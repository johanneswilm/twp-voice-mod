"""Build the language mod from the user's OWN pulled APK + OBB.

Usage: python3 build_mod.py <pulled.apk> [pulled.obb]

- derives versionCode from the APK; the mod OBB is named main.<vc>.<pkg>.obb
- patches the APK's own arm64 libThimbleweedPark.so (auto-derives all patch
  addresses; if the lib is identical to the known 1.0.10 build the already
  validated patched_arm64.so is reused)
- appends the German/Spanish audio entries to the given OBB (or the one
  embedded in the APK if none given)
- produces dist_from_phone/ThimbleweedPark-mod-<vc>.apk and matching OBB
"""
import os
import shutil
import struct
import subprocess
import sys
import zipfile

from ggpack3 import GGPack
from ggpack_write import GGPackWriter
import so_patch

BT = '/tmp/bt/android-14'
KS = 'mod.keystore'
KS_PASS = 'twpmodpass'
PKG = 'com.terribletoybox.thimbleweedparkandroid'
OUTDIR = 'dist_from_phone'


def version_code(apk_path):
    from pyaxmlparser import APK
    a = APK(apk_path)
    return int(a.version_code), a.package


def get_arm64_lib(apk_path):
    with zipfile.ZipFile(apk_path) as z:
        return z.read('lib/arm64-v8a/libThimbleweedPark.so')


def make_keystore():
    if not os.path.exists(KS):
        subprocess.run(['keytool', '-genkeypair', '-v', '-keystore', KS,
                        '-alias', 'twpmod', '-keyalg', 'RSA', '-keysize', '2048',
                        '-validity', '10000', '-storepass', KS_PASS,
                        '-keypass', KS_PASS, '-dname', 'CN=TWP Language Mod'],
                       check=True, capture_output=True)


def patch_lib(apk_path, out_path):
    lib = get_arm64_lib(apk_path)
    known = open('apk_extracted/lib/arm64-v8a/libThimbleweedPark.so', 'rb').read()
    if lib == known:
        shutil.copyfile('patched_arm64.so', out_path)
        print('lib matches known 1.0.10 build -> reused validated patch')
    else:
        print('lib differs from known build -> auto-patching this build')
        open('/tmp/their_lib.so', 'wb').write(lib)
        so_patch.apply_patch_auto('/tmp/their_lib.so', out_path)
    # optional second pass: OBB-from-APK fallback (experimental, see so_patch_obb)
    # TWP_EXTRACTION=1 builds the self-extracting variant instead (wrapper dex
    # copies assets/obb out on first launch; native patch not needed).
    if os.environ.get('TWP_EXTRACTION') != '1':
        import so_patch_obb
        so_patch_obb.apply(out_path, out_path,
                           pristine_path='apk_extracted/lib/arm64-v8a/libThimbleweedPark.so')
        shutil.copyfile(out_path, 'patched_arm64.so')  # keep cached patch current


def repack_apk(apk_path, patched_lib_path, obb_path, out_apk):
    """obb_path=None -> keep whatever assets/obb the apk had (or none)."""
    build = 'apk_build_theirs'
    if os.path.exists(build):
        shutil.rmtree(build)
    os.makedirs(build)
    with zipfile.ZipFile(apk_path) as z:
        for n in z.namelist():
            if n.startswith('META-INF/'):
                continue
            z.extract(n, build)
    shutil.copyfile(patched_lib_path, f'{build}/lib/arm64-v8a/libThimbleweedPark.so')
    if obb_path is not None:
        shutil.copyfile(obb_path, f'{build}/assets/obb')
    # optional wrapper dex with the assets/obb -> external OBB self-extraction hook
    wrapper_dex = '/tmp/classes_patched.dex'
    if os.path.exists(wrapper_dex):
        shutil.copyfile(wrapper_dex, f'{build}/classes.dex')
    unsigned = out_apk + '.unsigned'
    with zipfile.ZipFile(unsigned, 'w') as z:
        for root, dirs, files in os.walk(build):
            for f in sorted(files):
                p = os.path.join(root, f)
                arc = os.path.relpath(p, build)
                # Android 11+ requires resources.arsc stored uncompressed+aligned;
                # uncompressed native libs are page-aligned by zipalign -p
                stored = arc in ('assets/obb', 'resources.arsc') or arc.startswith('lib/')
                ctype = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                z.write(p, arc, compress_type=ctype)
    subprocess.run([f'{BT}/zipalign', '-f', '-p', '4', unsigned, out_apk + '.aligned'], check=True)
    make_keystore()
    subprocess.run([f'{BT}/apksigner', 'sign', '--ks', KS, '--ks-pass', f'pass:{KS_PASS}',
                    '--key-pass', f'pass:{KS_PASS}', '--out', out_apk, out_apk + '.aligned'], check=True)
    r = subprocess.run([f'{BT}/apksigner', 'verify', out_apk], capture_output=True, text=True)
    print('apksigner verify:', (r.stdout or r.stderr).strip()[:200])
    for p in (unsigned, out_apk + '.aligned'):
        if os.path.exists(p):
            os.unlink(p)


def append_lang_files(obb_in, obb_out):
    pack = GGPack(obb_in)
    existing = {k.lower() for k in pack.entries}
    w = GGPackWriter(obb_in)
    added = 0
    for lang in ('de', 'es'):
        d = os.path.join('tts_out', lang)
        for fn in sorted(os.listdir(d)):
            base, ext = os.path.splitext(fn)
            actor_id, langpart = base.rsplit('_', 1)
            actor, oid = actor_id.rsplit('_', 1)
            name = f'{actor}_{oid}_{langpart}{ext}'
            if name.lower() in existing:
                continue
            with open(os.path.join(d, fn), 'rb') as fh:
                w.add_entry(name, fh.read())
            added += 1
    print(f'appending {added} lang entries to {obb_in}')
    w.write(obb_out)
    pk = GGPack(obb_out)
    print('modded obb entries:', len(pk.entries))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    no_embed = '--no-embed-obb' in sys.argv
    apk_path = args[0]
    vc, package = version_code(apk_path)
    print(f'pulled APK: {apk_path}  versionCode={vc} package={package}')
    assert package == PKG, 'unexpected package name'
    os.makedirs(OUTDIR, exist_ok=True)

    obb_path = sys.argv[2] if len(sys.argv) > 2 else None
    if obb_path is None:
        print('no OBB given -> extracting embedded assets/obb from APK')
        with zipfile.ZipFile(apk_path) as z:
            z.extract('assets/obb', '/tmp/their_obb_dir')
        obb_path = '/tmp/their_obb_dir/assets/obb'
    assert os.path.exists(obb_path), 'obb not found'

    lib_out = os.path.join(OUTDIR, 'libThimbleweedPark.patched.so')
    patch_lib(apk_path, lib_out)

    obb_base = os.path.basename(obb_path)
    if obb_base == 'obb':  # extracted from APK
        obb_base = f'main.{vc}.{PKG}.obb'
    obb_out = os.path.join(OUTDIR, obb_base)
    append_lang_files(obb_path, obb_out)

    out_apk = os.path.join(OUTDIR, f'ThimbleweedPark-mod-{vc}.apk')
    if no_embed:
        repack_apk(apk_path, lib_out, None, out_apk)
    else:
        repack_apk(apk_path, lib_out, obb_out, out_apk)
    print('done:')
    print(' ', out_apk, os.path.getsize(out_apk) // (1 << 20), 'MB')
    print(' ', obb_out, os.path.getsize(obb_out) // (1 << 20), 'MB',
          '-> install as', obb_base)


if __name__ == '__main__':
    main()
