# Combined single-APK distribution: reading the OBB straight out of the APK

The Android engine (1.0.10) opens its data pack (the OBB) only from the
external expansion-file path and ignores an `assets/obb` embedded in the APK
("Can't open file '<...>/main.65.<pkg>.obb'"). Embedding + extracting would
duplicate ~1.5 GB of storage permanently. Instead, the engine itself is
patched to serve the pack bytes straight out of the installed APK:

- `ObbExtract.smali` (hooked as the first statement of the wrapper activity's
  `onCreate`) writes a small `<obb path>.ref` file next to where the OBB
  would live, containing three lines: the APK path (getPackageCodePath),
  the embedded start offset and the embedded length - both from
  `AssetManager.openFd("obb")` (valid because the asset is ZIP_STORED).
  With a normal external OBB (split install), `openFd("obb")` throws and
  this is a no-op.
- `so_patch_obb.py` (second pass in build_mod.py) redirects every direct
  `bl <plt>` call site of fopen / fseek / stat / fclose in the engine's
  .text to thunks in a code cave:
    - hook_fopen:  real fopen first; on failure, look for "<path>.ref"; if
      present, fopen the APK and seek to the embedded offset
    - hook_fseek:  for the fallback FILE*, SEEK_SET += offset,
      SEEK_END -> offset+size (converted to SEEK_SET), SEEK_CUR unchanged
    - hook_stat:   the pack loader stats the pack when its size is unknown;
      on failure with the fallback active, synthesize a stat buffer with
      st_size at the bionic offset 48
    - hook_fclose: clear the fallback handle
  Everything else passes through untouched. The thunks call real libc
  through the original PLT stubs (call sites are redirected, not GOT
  entries, so RELRO does not matter). Globals (32 bytes) live in the
  writable padding after .bss.

`verify_obb_cave.py` emulates the thunks under unicorn with a fake libc and
checks the fallback, the seek math, the stat synthesis and the split-layout
no-op path.

## Rebuilding the wrapper dex

    apktool d base.apk -o work
    cp wrapper_patch/ObbExtract.smali work/smali/com/terribletoybox/thimbleweedparkandroid/
    # in work/smali/.../ThimbleweedPark.smali, insert as the first statement
    # of onCreate (right after .locals):
    #   invoke-static {p0}, Lcom/terribletoybox/thimbleweedparkandroid/ObbExtract;->ensure(Landroid/content/Context;)V
    apktool b work -o rebuilt.apk
    # take classes.dex out of rebuilt.apk and place it at /tmp/classes_patched.dex;
    # build_mod.py then swaps it into every repack automatically.

## Pitfalls (each cost a debugging cycle)

- apktool 2.9's tree-walking smali builder mis-compiles hand-written smali
  with loops + catch ranges; assemble with its bundled standalone smali
  (java -cp apktool.jar com.android.tools.smali.smali.Main) or keep the
  code shapes it tolerates.
- `new-array` + adjacent labels break apktool's tree builder; the shipped
  class avoids buffer loops entirely via FileChannel.transferTo.
- Two long invocation parameters need `invoke-virtual/range` with a
  consecutive register window - otherwise ART rejects the class
  (VerifyError) at load.
- A label directly after `new-array` and non-numeric label suffixes
  (`:cond_copy` vs `:cond_0`) also trip the tree builder.
- Recipients install one ~1.5 GB APK; the installed footprint is 1.5 GB
  (no extraction, no duplicate). The installer still demands ~2x free
  space during the install itself.
