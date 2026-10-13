# Self-extracting OBB wrapper (combined single-APK builds)

The Android engine (v1.0.10) loads its data pack only from the external
expansion-file path (`Android/obb/<pkg>/main.65.<pkg>.obb`) and ignores an
`assets/obb` embedded in the APK. To ship the mod as one self-contained APK,
the wrapper activity must copy the embedded blob out on first launch.

`ObbExtract.smali` is a small helper class (original code, LGPL-3.0 like the
rest of this repository) that:

1. computes the expected target `<obb-dir>/main.65.<package>.obb`,
2. skips the copy if the target already matches the embedded asset's size,
3. otherwise copies `assets/obb` to `<target>.twp` via
   `FileChannel.transferTo`, verifies the byte count, and renames it into
   place (an aborted copy never leaves a partial file at the real path),
4. swallows all errors so the game falls back to its own "Can't open file"
   message if extraction was impossible (e.g. no space).

## Applying it

    apktool d base.apk -o work
    cp wrapper_patch/ObbExtract.smali work/smali/com/terribletoybox/thimbleweedparkandroid/
    # in work/smali/.../ThimbleweedPark.smali, insert as the first statement
    # of onCreate (right after .locals):
    #   invoke-static {p0}, Lcom/terribletoybox/thimbleweedparkandroid/ObbExtract;->ensure(Landroid/content/Context;)V
    apktool b work -o rebuilt.apk
    # take classes.dex out of rebuilt.apk and place it at /tmp/classes_patched.dex;
    # build_mod.py then swaps it into every repack automatically.

## Notes

- apktool's own tree-walking smali builder (2.9.x) fails on the loop-based
  variant of this class; the shipped version uses `FileChannel.transferTo`
  and assembles cleanly. If you extend the class, avoid `new-array` and
  keep `long` invocation arguments in consecutive registers (two long
  parameters need `invoke-virtual/range` with a consecutive register window).
- The first launch of a combined APK copies ~1.5 GB and shows a black screen
  for a minute or so before the engine starts. Recipients need free storage
  for the APK plus the extracted copy (~3.1 GB total).
