#!/usr/bin/env python3
"""Seamless 3D volumetric 'hero' background loops (gas / nebula) rendered with Blender Cycles. docs/HERO_LOOPS_3D.md.

Runs INSIDE Blender (headless):
  blender -b -P backend/scripts/blender_hero_loops.py -- --out DIR [--palette brand|ember|aurora] [--mode dark|light] [--seed 7]
          [--res 3840x2160] [--seconds 12] [--fps 30] [--samples 96] [--device CPU|METAL|OPTIX|CUDA|AUTO]
          [--start 1 --end N] [--denoiser OPENIMAGEDENOISE|OPTIX] [--format PNG|JPEG]
or as a module with the pip `bpy` wheel (same arguments after `--`).

How the loop is seamless: every animated quantity is a function of theta = 2*pi*(frame-1)/N, so frame N+1 equals frame 1.
* the density field is a 4D noise sampled on a CIRCLE in (z, w): z = R*cos(theta), w = R*sin(theta): the gas churns and morphs (it does not just slide) and returns exactly;
* the camera drifts on a small ellipse (period = the loop), the scene is otherwise static.
Text safety: a soft clearing is cut into the gas around the camera axis (density x clear_floor in the middle, 1.0 near the edges), so titles and captions sit on a
calm, dark centre; crops to 9:16 and 1:1 keep that calm centre. All noise offsets come from --seed; all colours from --palette.
Licensing: the output is a render of our own procedural scene (Blender is GPL software, its renders are ours).
"""
import argparse
import math
import os
import sys

import bpy  # noqa: E402  (Blender's python)

PALETTES = {   # (position, (r, g, b)) linear-ish sRGB values 0..1, dark to bright; the emission ramp
    "brand": [(0.00, (0.010, 0.012, 0.060)), (0.30, (0.080, 0.090, 0.480)), (0.55, (0.270, 0.200, 0.780)), (0.78, (0.560, 0.330, 0.930)), (1.00, (0.350, 0.900, 1.000))],
    "ember": [(0.00, (0.050, 0.004, 0.004)), (0.30, (0.450, 0.030, 0.020)), (0.60, (0.950, 0.220, 0.040)), (0.85, (1.000, 0.550, 0.120)), (1.00, (1.000, 0.850, 0.550))],
    "aurora": [(0.00, (0.004, 0.030, 0.040)), (0.30, (0.010, 0.250, 0.300)), (0.60, (0.050, 0.700, 0.500)), (0.85, (0.300, 0.900, 0.700)), (1.00, (0.750, 1.000, 0.900))],
}
# Light mode: the gas is a coloured filter over a pale world (it absorbs what is not its colour), so the ramp holds the TRANSMITTED colour, thin gas to dense gas.
LIGHT_PALETTES = {
    "brand": [(0.00, (0.780, 0.800, 1.000)), (0.35, (0.600, 0.620, 1.000)), (0.60, (0.720, 0.520, 1.000)), (0.82, (0.960, 0.560, 0.900)), (1.00, (0.450, 0.850, 1.000))],
    "ember": [(0.00, (1.000, 0.860, 0.740)), (0.35, (1.000, 0.700, 0.520)), (0.60, (1.000, 0.520, 0.450)), (0.82, (1.000, 0.640, 0.300)), (1.00, (1.000, 0.820, 0.400))],
    "aurora": [(0.00, (0.740, 0.960, 0.900)), (0.35, (0.480, 0.900, 0.800)), (0.60, (0.380, 0.800, 0.900)), (0.82, (0.520, 0.920, 0.640)), (1.00, (0.800, 1.000, 0.700))],
}
# The world behind the gas, per palette: a black with the palette's own tint (a navy black behind orange gas reads as mud), a paper with a hint of the hue.
WORLD = {
    "dark": {"brand": (0.003, 0.004, 0.016), "ember": (0.007, 0.002, 0.002), "aurora": (0.002, 0.008, 0.012)},
    "light": {"brand": (0.930, 0.940, 0.985), "ember": (0.985, 0.950, 0.925), "aurora": (0.925, 0.975, 0.960)},
}


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--palette", default="brand", choices=sorted(PALETTES))
    ap.add_argument("--mode", default="dark", choices=["dark", "light"])
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--res", default="3840x2160")
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--samples", type=int, default=96)
    ap.add_argument("--device", default="AUTO")
    ap.add_argument("--denoiser", default="OPENIMAGEDENOISE")
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--format", default="PNG")
    ap.add_argument("--density", type=float, default=1.0)
    ap.add_argument("--clear-floor", type=float, default=0.04)
    ap.add_argument("--step-rate", type=float, default=1.5)
    ap.add_argument("--emission", type=float, default=1.5)
    ap.add_argument("--no-render", action="store_true")
    return ap.parse_args(argv)


def build(a):
    n_frames = int(round(a.seconds * a.fps))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    w, h = [int(x) for x in a.res.lower().split("x")]
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    sc.render.fps = a.fps
    sc.frame_start, sc.frame_end = 1, n_frames
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = a.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    cy.denoiser = a.denoiser
    cy.volume_step_rate = a.step_rate
    cy.volume_max_steps = 256
    cy.max_bounces = 2
    cy.volume_bounces = 0
    cy.film_exposure = 1.0
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.image_settings.file_format = a.format
    if a.format == "PNG":
        sc.render.image_settings.color_depth = "16"
        sc.render.image_settings.compression = 15
    else:
        sc.render.image_settings.quality = 97
    sc.render.film_transparent = False
    sc.render.use_motion_blur = False

    # --- device
    prefs = bpy.context.preferences.addons["cycles"].preferences
    want = a.device.upper()
    if want == "CPU":
        sc.cycles.device = "CPU"
    else:
        order = [want] if want != "AUTO" else ["OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"]
        picked = None
        for kind in order:
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                devs = [d for d in prefs.devices if d.type == kind]
                if devs:
                    for d in prefs.devices:
                        d.use = d.type == kind or d.type == "CPU" and kind == "METAL"
                    picked = kind
                    break
            except Exception:
                continue
        sc.cycles.device = "GPU" if picked else "CPU"
        print("[hero] device:", picked or "CPU")

    # --- world
    world = bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (*WORLD[a.mode][a.palette], 1.0)
    bg.inputs[1].default_value = 1.0

    # --- the volume box (the camera looks through it)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
    box = bpy.context.object
    box.name = "GasBox"
    box.scale = (34.0, 3.2, 20.0)
    mat = bpy.data.materials.new("Gas")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    box.data.materials.append(mat)
    N = nt.nodes
    L = nt.links

    def node(kind, x, y, **kw):
        nd = N.new(kind)
        nd.location = (x, y)
        for k, v in kw.items():
            setattr(nd, k, v)
        return nd

    out = node("ShaderNodeOutputMaterial", 1500, 0)
    vol = node("ShaderNodeVolumePrincipled", 1250, 0)
    L.new(vol.outputs[0], out.inputs["Volume"])
    tc = node("ShaderNodeTexCoord", -1200, 0)
    # loop drivers (updated by a frame handler): z offset and w
    zoff = node("ShaderNodeValue", -1200, -300)
    woff = node("ShaderNodeValue", -1200, -420)
    zoff.outputs[0].default_value = 0.0
    woff.outputs[0].default_value = 0.0
    rng = (a.seed * 17.31) % 97.0
    mp = node("ShaderNodeMapping", -1000, 0)
    FEAT = 0.24   # noise cycles per scene unit (object coordinates of the unit cube run -0.5..0.5, so scale by the box size)
    mp.inputs["Scale"].default_value = (34.0 * FEAT, 3.2 * FEAT, 20.0 * FEAT)
    mp.inputs["Location"].default_value = (rng, rng * 0.37, rng * 0.61)
    L.new(tc.outputs["Object"], mp.inputs["Vector"])
    comb = node("ShaderNodeCombineXYZ", -800, -250)
    L.new(zoff.outputs[0], comb.inputs["Z"])
    add0 = node("ShaderNodeVectorMath", -600, 0, operation="ADD")
    L.new(mp.outputs[0], add0.inputs[0])
    L.new(comb.outputs[0], add0.inputs[1])
    # domain warp: a slower, larger noise bends the lookup of the main noise
    warp = node("ShaderNodeTexNoise", -400, 250, noise_dimensions="4D")
    warp.inputs["Scale"].default_value = 0.55
    warp.inputs["Detail"].default_value = 2.0
    warp.inputs["Roughness"].default_value = 0.5
    L.new(add0.outputs[0], warp.inputs["Vector"])
    L.new(woff.outputs[0], warp.inputs["W"])
    wsub = node("ShaderNodeVectorMath", -200, 250, operation="SUBTRACT")
    wsub.inputs[1].default_value = (0.5, 0.5, 0.5)
    L.new(warp.outputs["Color"], wsub.inputs[0])
    wscale = node("ShaderNodeVectorMath", -50, 250, operation="SCALE")
    wscale.inputs["Scale"].default_value = 3.6
    L.new(wsub.outputs[0], wscale.inputs[0])
    add1 = node("ShaderNodeVectorMath", 100, 100, operation="ADD")
    L.new(add0.outputs[0], add1.inputs[0])
    L.new(wscale.outputs[0], add1.inputs[1])
    main = node("ShaderNodeTexNoise", 300, 100, noise_dimensions="4D")
    main.inputs["Scale"].default_value = 1.0
    main.inputs["Detail"].default_value = 8.0
    main.inputs["Roughness"].default_value = 0.66
    main.inputs["Lacunarity"].default_value = 2.1
    L.new(add1.outputs[0], main.inputs["Vector"])
    L.new(woff.outputs[0], main.inputs["W"])
    # density shaping: wisps and voids
    shape = node("ShaderNodeMapRange", 520, 100)
    shape.inputs["From Min"].default_value = 0.48
    shape.inputs["From Max"].default_value = 0.70
    shape.inputs["To Min"].default_value = 0.0
    shape.inputs["To Max"].default_value = 1.0
    shape.interpolation_type = "SMOOTHSTEP"
    L.new(main.outputs["Fac"], shape.inputs["Value"])
    # clearing around the camera axis (object x, z): calm centre for text
    sep = node("ShaderNodeSeparateXYZ", -800, -600)
    L.new(tc.outputs["Object"], sep.inputs[0])
    xx = node("ShaderNodeMath", -600, -560, operation="MULTIPLY")
    zz = node("ShaderNodeMath", -600, -680, operation="MULTIPLY")
    L.new(sep.outputs["X"], xx.inputs[0]); L.new(sep.outputs["X"], xx.inputs[1])
    L.new(sep.outputs["Z"], zz.inputs[0]); L.new(sep.outputs["Z"], zz.inputs[1])
    # the box is 34 x 20 in object units scaled; object coords of a unit cube go -0.5..0.5, so x in box units = x*34, z = z*20
    # world-size ellipse: ((x*34)/(rx))^2 + ((z*20)/(rz))^2
    ex = node("ShaderNodeMath", -400, -560, operation="MULTIPLY"); ex.inputs[1].default_value = (34.0 / 9.5) ** 2   # rx = 9.5 units
    ez = node("ShaderNodeMath", -400, -680, operation="MULTIPLY"); ez.inputs[1].default_value = (20.0 / 5.5) ** 2   # rz = 5.5 units
    L.new(xx.outputs[0], ex.inputs[0]); L.new(zz.outputs[0], ez.inputs[0])
    esum = node("ShaderNodeMath", -200, -620, operation="ADD")
    L.new(ex.outputs[0], esum.inputs[0]); L.new(ez.outputs[0], esum.inputs[1])
    esq = node("ShaderNodeMath", -50, -620, operation="SQRT")
    L.new(esum.outputs[0], esq.inputs[0])
    clr = node("ShaderNodeMapRange", 120, -620)
    clr.interpolation_type = "SMOOTHSTEP"
    clr.inputs["From Min"].default_value = 0.45
    clr.inputs["From Max"].default_value = 1.35
    clr.inputs["To Min"].default_value = a.clear_floor
    clr.inputs["To Max"].default_value = 1.0
    L.new(esq.outputs[0], clr.inputs["Value"])
    # soft fade at the box faces so no hard edge shows
    dens = node("ShaderNodeMath", 760, 0, operation="MULTIPLY")
    L.new(shape.outputs["Result"], dens.inputs[0])
    L.new(clr.outputs["Result"], dens.inputs[1])
    dscale = node("ShaderNodeMath", 940, 0, operation="MULTIPLY")
    dscale.inputs[1].default_value = 0.55 * a.density
    L.new(dens.outputs[0], dscale.inputs[0])
    L.new(dscale.outputs[0], vol.inputs["Density"])
    # emission colour from a palette ramp driven by the density-ish field + a second slow noise
    ramp = node("ShaderNodeValToRGB", 760, -250)
    cr = ramp.color_ramp
    stops = (LIGHT_PALETTES if a.mode == "light" else PALETTES)[a.palette]
    while len(cr.elements) > 2:
        cr.elements.remove(cr.elements[-1])
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1.0)
    cr.elements[1].position, cr.elements[1].color = stops[1][0], (*stops[1][1], 1.0)
    for pos, col in stops[2:]:
        e = cr.elements.new(pos)
        e.color = (*col, 1.0)
    mixv = node("ShaderNodeMix", 620, -250, data_type="FLOAT")
    mixv.inputs[0].default_value = 0.45
    L.new(shape.outputs["Result"], mixv.inputs[2])
    L.new(main.outputs["Fac"], mixv.inputs[3])
    L.new(mixv.outputs[0], ramp.inputs["Fac"])
    if a.mode == "dark":
        vol.inputs["Color"].default_value = (0.8, 0.85, 1.0, 1.0)
        L.new(ramp.outputs["Color"], vol.inputs["Emission Color"])
        # Principled Volume emission does NOT follow density: scale it by the shaped density ourselves or the whole box glows evenly
        es = node("ShaderNodeMath", 1100, -400, operation="MULTIPLY")
        es.inputs[1].default_value = a.emission
        L.new(dens.outputs[0], es.inputs[0])
        L.new(es.outputs[0], vol.inputs["Emission Strength"])
        vol.inputs["Absorption Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        vol.inputs["Anisotropy"].default_value = 0.3
    else:   # light: a coloured FILTER over a pale world: pure absorption (Volume Absorption: what is not the ramp's colour is absorbed), no emission, no scattering.
        # Two things that did not work: Principled Volume with a white Color absorbs nothing (a grey haze), and with the ramp as its Color it also scatters,
        # which washes the hue out to a dirty mauve.
        absorb = node("ShaderNodeVolumeAbsorption", 1250, -300)
        L.new(ramp.outputs["Color"], absorb.inputs["Color"])
        L.new(dscale.outputs[0], absorb.inputs["Density"])
        L.new(absorb.outputs[0], out.inputs["Volume"])
        dscale.inputs[1].default_value = 0.35 * a.density

    # --- camera: slow ellipse, looking along +y through the box
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 38
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.rotation_euler = (math.radians(90), 0, 0)
    sc.camera = cam

    R = 0.8   # radius of the (z, w) circle in noise space: larger = faster churn
    DRIFT_X, DRIFT_Z, CAM_Y = 0.9, 0.55, -13.0

    def apply(frame):
        th = 2.0 * math.pi * ((frame - 1) % n_frames) / n_frames
        zoff.outputs[0].default_value = R * math.cos(th)
        woff.outputs[0].default_value = R * math.sin(th)
        cam.location = (DRIFT_X * math.sin(th), CAM_Y + 0.35 * math.cos(th), DRIFT_Z * math.sin(th + 1.2))

    def on_frame(scene, depsgraph=None):
        apply(scene.frame_current)
    bpy.app.handlers.frame_change_pre.clear()
    bpy.app.handlers.frame_change_pre.append(on_frame)
    apply(1)
    return sc, n_frames


def main():
    a = parse()
    os.makedirs(a.out, exist_ok=True)
    sc, n = build(a)
    end = a.end or n
    ext = "png" if a.format == "PNG" else "jpg"
    if a.no_render:
        return
    import time
    for f in range(a.start, end + 1):
        sc.frame_set(f)
        sc.render.filepath = os.path.join(a.out, f"f_{f:04d}.{ext}")
        t = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"[hero] frame {f}/{n} {time.time() - t:.1f}s", flush=True)


if __name__ == "__main__":
    main()
