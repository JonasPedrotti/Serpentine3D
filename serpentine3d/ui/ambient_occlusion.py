"""Screen-space ambient occlusion: creases, corners and contacts darkened
the way soft daylight darkens them on a plaster model.

The pane draws straight into Qt's framebuffer, which keeps its depth to
itself, so the opaque faces of the frame are drawn a second time into a
depth texture of our own. The occlusion is worked out from that depth
alone, the normal rebuilt from neighbouring pixels, then blurred without
bleeding across silhouettes and multiplied over the finished picture.

Soft rather than strong: a grainy shadow reads as a fault in the model, so
the noise is evened out completely and the darkening kept gentle.
"""

from __future__ import annotations

import ctypes

import numpy as np
from OpenGL import GL
from OpenGL.raw.GL.VERSION.GL_1_0 import glTexImage2D as _raw_tex_image_2d

KERNEL_SIZE = 24
#: How far round a point is searched for what hides it, in screen pixels,
#: so the shading reads the same at any zoom.
RADIUS_PX = 60.0
#: How hard the occlusion is curved, then how much of it reaches the picture.
STRENGTH = 1.2
AMOUNT = 0.5

QUAD_VERT = """
#version 330 core
layout(location=0) in vec2 pos;
void main() { gl_Position = vec4(pos, 0.0, 1.0); }
"""

_VIEW_POS = """
uniform sampler2D uDepth;
uniform mat4 uInvProj;
vec3 viewPos(vec2 uv) {
    float d = texture(uDepth, uv).r;
    vec4 v = uInvProj * vec4(uv * 2.0 - 1.0, d * 2.0 - 1.0, 1.0);
    return v.xyz / v.w;
}
"""

SSAO_FRAG = """
#version 330 core
uniform mat4 uProj;
uniform vec2 uTexel;
uniform float uRadiusPx;
uniform float uPxToView;    // view units per pixel at clip w = 1
uniform vec3 uKernel[KERNEL];
out vec4 frag;
VIEW_POS
void main() {
    vec2 uv = gl_FragCoord.xy * uTexel;
    if (texture(uDepth, uv).r >= 1.0) { frag = vec4(1.0); return; }
    vec3 P = viewPos(uv);
    vec3 r = viewPos(uv + vec2(uTexel.x, 0.0));
    vec3 l = viewPos(uv - vec2(uTexel.x, 0.0));
    vec3 t = viewPos(uv + vec2(0.0, uTexel.y));
    vec3 b = viewPos(uv - vec2(0.0, uTexel.y));
    // the nearer neighbour on each side, so a silhouette does not bend it
    vec3 dx = abs(r.z - P.z) < abs(P.z - l.z) ? r - P : P - l;
    vec3 dy = abs(t.z - P.z) < abs(P.z - b.z) ? t - P : P - b;
    vec3 N = normalize(cross(dx, dy));

    float w = (uProj * vec4(P, 1.0)).w;
    float radius = uRadiusPx * uPxToView * w;
    float bias = radius * 0.05;

    // a 4x4 tile of rotations, which the blur's 4x4 window evens out
    ivec2 cell = ivec2(gl_FragCoord.xy) % 4;
    float ang = (float(cell.x + cell.y * 4) + 0.5) * 0.392699;
    vec3 rv = vec3(cos(ang), sin(ang), 0.0);
    vec3 T = normalize(rv - N * dot(rv, N));
    mat3 tbn = mat3(T, cross(N, T), N);

    float occ = 0.0;
    for (int i = 0; i < KERNEL; ++i) {
        vec3 S = P + tbn * uKernel[i] * radius;
        vec4 o = uProj * vec4(S, 1.0);
        vec2 suv = o.xy / o.w * 0.5 + 0.5;
        if (any(lessThan(suv, vec2(0.0))) || any(greaterThan(suv, vec2(1.0))))
            continue;
        float sz = viewPos(suv).z;
        float near = 1.0 - smoothstep(0.5 * radius, radius, abs(P.z - sz));
        occ += (sz >= S.z + bias ? 1.0 : 0.0) * near;
    }
    float ao = 1.0 - occ / float(KERNEL);
    // a face seen almost edge-on has too few pixels to say what hides it
    vec3 V = uProj[3][3] == 0.0 ? normalize(-P) : vec3(0.0, 0.0, 1.0);
    ao = mix(1.0, ao, smoothstep(0.08, 0.3, abs(dot(N, V))));
    frag = vec4(vec3(clamp(ao, 0.0, 1.0)), 1.0);
}
""".replace("VIEW_POS", _VIEW_POS).replace("KERNEL", str(KERNEL_SIZE))

# Half of a separable 8x8 blur, run across and then down: eight taps cover
# two whole 4x4 tiles of rotations, so their pattern averages out exactly.
# A tap weighs less the further it lies in depth, so the shading of one
# surface never bleeds onto another behind it. The second run is the one
# that lands on the picture, shaped by the strength and amount.
BLUR_FRAG = """
#version 330 core
uniform sampler2D uAO;
uniform mat4 uProj;
uniform vec2 uTexel;
uniform vec2 uDir;
uniform float uPxToView;
uniform int uFinal;
uniform float uStrength;
uniform float uAmount;
out vec4 frag;
VIEW_POS
void main() {
    vec2 uv = gl_FragCoord.xy * uTexel;
    if (texture(uDepth, uv).r >= 1.0) { frag = vec4(1.0); return; }
    vec3 P = viewPos(uv);
    float tol = 4.0 * uPxToView * (uProj * vec4(P, 1.0)).w;
    float sum = 0.0;
    float weight = 0.0;
    for (int i = -4; i < 4; ++i) {
        vec2 suv = uv + uDir * float(i) * uTexel;
        float dz = (viewPos(suv).z - P.z) / tol;
        float wgt = exp(-dz * dz);
        sum += texture(uAO, suv).r * wgt;
        weight += wgt;
    }
    float ao = sum / max(weight, 1e-6);
    if (uFinal == 1)
        ao = mix(1.0, pow(ao, uStrength), uAmount);
    frag = vec4(vec3(ao), 1.0);
}
""".replace("VIEW_POS", _VIEW_POS)


def kernel(count: int = KERNEL_SIZE, seed: int = 7) -> np.ndarray:
    """Points in the unit hemisphere round +z, more of them close in, where
    what hides a point matters most."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(count):
        v = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1),
                      rng.uniform(0.15, 1)])
        v /= np.linalg.norm(v)
        t = i / count
        v *= rng.uniform(0.6, 1.0) * (0.25 + 0.75 * t)
        out.append(v)
    return np.asarray(out, np.float32)


def _compile(vert_src: str, frag_src: str) -> int:
    from .viewport import _compile as compile_
    return compile_(vert_src, frag_src)


class AmbientOcclusion:
    """The textures and programs for one GL context. Made in that context,
    and dropped with it."""

    def __init__(self):
        self.ssao_prog = _compile(QUAD_VERT, SSAO_FRAG)
        self.blur_prog = _compile(QUAD_VERT, BLUR_FRAG)
        quad = np.array([-1, -1, 1, -1, -1, 1, 1, 1], np.float32)
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, quad.nbytes, quad,
                        GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 2, GL.GL_FLOAT, False, 0,
                                 ctypes.c_void_p(0))
        GL.glBindVertexArray(0)
        self.size = (0, 0)
        self.depth_fbo = self.depth_tex = 0
        self.ao_fbo = self.ao_tex = 0
        self.blur_fbo = self.blur_tex = 0
        GL.glUseProgram(self.ssao_prog)
        GL.glUniform3fv(GL.glGetUniformLocation(self.ssao_prog, "uKernel"),
                        KERNEL_SIZE, kernel())
        GL.glUseProgram(0)

    def _texture(self, internal, fmt, kind, w, h):
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        # unwrapped: PyOpenGL has no array type for a packed depth-stencil
        _raw_tex_image_2d(GL.GL_TEXTURE_2D, 0, internal, w, h, 0, fmt, kind,
                          None)
        for p in (GL.GL_TEXTURE_MIN_FILTER, GL.GL_TEXTURE_MAG_FILTER):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, p, GL.GL_NEAREST)
        for p in (GL.GL_TEXTURE_WRAP_S, GL.GL_TEXTURE_WRAP_T):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, p, GL.GL_CLAMP_TO_EDGE)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return tex

    def _resize(self, w: int, h: int):
        self._release_targets()
        # with a stencil, which the section caps are laid in by
        self.depth_tex = self._texture(GL.GL_DEPTH24_STENCIL8,
                                       GL.GL_DEPTH_STENCIL,
                                       GL.GL_UNSIGNED_INT_24_8, w, h)
        self.depth_fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.depth_fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER,
                                  GL.GL_DEPTH_STENCIL_ATTACHMENT,
                                  GL.GL_TEXTURE_2D, self.depth_tex, 0)
        GL.glDrawBuffer(GL.GL_NONE)
        GL.glReadBuffer(GL.GL_NONE)
        # half floats, so a faint gradient does not step into bands
        self.ao_tex, self.ao_fbo = self._colour_target(w, h)
        self.blur_tex, self.blur_fbo = self._colour_target(w, h)
        for fbo in (self.depth_fbo, self.ao_fbo, self.blur_fbo):
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
            status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
            if status != GL.GL_FRAMEBUFFER_COMPLETE:
                self._release_targets()
                raise RuntimeError(f"ambient occlusion target incomplete "
                                   f"({status:#x})")
        self.size = (w, h)

    def _colour_target(self, w, h):
        tex = self._texture(GL.GL_R16F, GL.GL_RED, GL.GL_FLOAT, w, h)
        fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                  GL.GL_TEXTURE_2D, tex, 0)
        return tex, fbo

    def begin_depth(self, w: int, h: int):
        """Bind the depth target, cleared, for the frame's opaque faces."""
        if self.size != (w, h):
            self._resize(w, h)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.depth_fbo)
        GL.glViewport(0, 0, w, h)
        GL.glDepthMask(True)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT | GL.GL_STENCIL_BUFFER_BIT)

    def apply(self, target_fbo: int, viewport, proj: np.ndarray,
              pixel_ratio: float = 1.0):
        """Work the occlusion out and darken `target_fbo` by it."""
        w, h = self.size
        proj = np.asarray(proj, np.float64)
        inv = np.linalg.inv(proj).astype(np.float32)
        proj32 = proj.astype(np.float32)
        px_to_view = 2.0 / (abs(proj[1, 1]) * h)
        texel = (1.0 / w, 1.0 / h)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(False)
        GL.glDisable(GL.GL_BLEND)
        GL.glBindVertexArray(self.vao)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.depth_tex)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.ao_fbo)
        GL.glViewport(0, 0, w, h)
        prog = self.ssao_prog
        GL.glUseProgram(prog)
        self._common(prog, proj32, inv, texel, px_to_view)
        GL.glUniform1f(GL.glGetUniformLocation(prog, "uRadiusPx"),
                       RADIUS_PX * pixel_ratio)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

        prog = self.blur_prog
        loc = GL.glGetUniformLocation
        GL.glUseProgram(prog)
        self._common(prog, proj32, inv, texel, px_to_view)
        GL.glUniform1i(loc(prog, "uAO"), 1)
        GL.glUniform1f(loc(prog, "uStrength"), STRENGTH)
        GL.glUniform1f(loc(prog, "uAmount"), AMOUNT)
        GL.glActiveTexture(GL.GL_TEXTURE1)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.blur_fbo)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.ao_tex)
        GL.glUniform2f(loc(prog, "uDir"), 1.0, 0.0)
        GL.glUniform1i(loc(prog, "uFinal"), 0)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, target_fbo)
        GL.glViewport(*viewport)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.blur_tex)
        GL.glUniform2f(loc(prog, "uDir"), 0.0, 1.0)
        GL.glUniform1i(loc(prog, "uFinal"), 1)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ZERO, GL.GL_SRC_COLOR)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glBindVertexArray(0)
        GL.glUseProgram(0)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDepthMask(True)
        GL.glEnable(GL.GL_DEPTH_TEST)

    @staticmethod
    def _common(prog, proj32, inv, texel, px_to_view):
        loc = GL.glGetUniformLocation
        GL.glUniformMatrix4fv(loc(prog, "uProj"), 1, GL.GL_TRUE, proj32)
        GL.glUniformMatrix4fv(loc(prog, "uInvProj"), 1, GL.GL_TRUE, inv)
        GL.glUniform2f(loc(prog, "uTexel"), *texel)
        GL.glUniform1f(loc(prog, "uPxToView"), px_to_view)
        GL.glUniform1i(loc(prog, "uDepth"), 0)

    def _release_targets(self):
        fbos = [f for f in (self.depth_fbo, self.ao_fbo, self.blur_fbo) if f]
        texs = [t for t in (self.depth_tex, self.ao_tex, self.blur_tex) if t]
        if fbos:
            GL.glDeleteFramebuffers(len(fbos), fbos)
        if texs:
            GL.glDeleteTextures(len(texs), texs)
        self.depth_fbo = self.depth_tex = self.ao_fbo = self.ao_tex = 0
        self.blur_fbo = self.blur_tex = 0
        self.size = (0, 0)
