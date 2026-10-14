# Combined single-file distribution: current status (experimental)

Two approaches exist for shipping the mod as ONE apk file. Neither is
verified end-to-end on a device yet; the SPLIT distribution (32 MB patched
apk + modded OBB pushed to Android/obb/<pkg>/) remains the recommended,
fully-working installation method.

## 1. Self-extracting APK (wrapper dex)

wrapper_patch/ObbExtract.smali (the version in this directory) copies
assets/obb out to the expansion-file path on first launch (temp file +
rename, size-check skip). Builds and assembles cleanly, BUT the shipped
copy has one remaining ART verifier rejection in copy() (a move-result-wide
overlapping a live reference register around the FileChannel transferTo -
same register-layout class of bug as documented below). It needs the same
one-line register remap; on-device it aborts with VerifyError at launch.

## 2. Deep patch: engine reads the OBB from inside the APK (so_patch_obb.py)

No extraction at all (1.5 GB installed footprint). The wrapper writes
<obb path>.ref (apk path, offset, length) and the patched engine falls back
to reading pack bytes from the APK when its fopen of the OBB fails.
Unicorn-verified (verify_obb_cave.py, 5/5) and the wrapper side proven on
device (.ref written correctly). The native side still SIGSEGVs on a real
device (fclose on a corrupted FILE* during engine init) for a reason not
yet isolated - the thunks preserve callee-saved registers per the harness,
and only the 31 genuine call sites are redirected, so the remaining suspect
is an interaction not covered by the emulation.

## Shared pitfalls (all hit in practice)

- Hand-written arm64: two long invocation parameters need
  invoke-virtual/range with a consecutive register window (ART VerifyError).
- move-result-wide into a register pair that overlaps a live reference
  triggers the same VerifyError class.
- stp/ldp scaled immediates only reach +/-504 - larger frame offsets silently
  wrap (masked imm7) and corrupt the saved-register pair.
- mov_reg with SP as the source emits XZR (ORR cannot encode SP) - use
  ADD Xd, SP, #0.
- apktool 2.9's smali tree builder miscompiles loops with catch ranges;
  assemble via its bundled standalone smali or restructure.
- The mid-.text "zero runs" are clusters of small zero holes with REAL code
  between them - a cave sized to the merged cluster overwrites live engine
  code. The sayline patch's two 304-byte slots are the only proven-safe
  cave locations in this binary.
