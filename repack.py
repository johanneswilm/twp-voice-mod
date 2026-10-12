"""Build the final modded deliverables.

1. repack_obb: append all generated <lang> audio/lipsync entries to the pack
   -> dist/main.81.com.terribletoybox.thimbleweedparkandroid.obb
2. repack_apk: swap the patched arm64 lib into the APK, replace the embedded
   assets/obb with the modded pack, re-zip, zipalign, sign (v1+v2 via apksigner)
   -> dist/ThimbleweedPark-mod.apk
"""
import os
import shutil
import struct
import subprocess
import sys
import zipfile

from ggpack3 import GGPack
from ggpack_write import GGPackWriter

OBB = 'main.65.com.terribletoybox.thimbleweedparkandroid.obb'
OUT_OBB = 'dist/main.81.com.terribletoybox.thimbleweedparkandroid.obb'
SRC_APK = 'Thimbleweed-Park-v1.0.10-full-apkvision.apk'
OUT_APK_UNSIGNED = 'dist/ThimbleweedPark-mod-unsigned.apk'
OUT_APK_ALIGNED = 'dist/ThimbleweedPark-mod-aligned.apk'
OUT_APK = 'dist/ThimbleweedPark-mod.apk'
PATCHED_SO = 'patched_arm64.so'
BT = '/tmp/bt/android-14'
KS = 'mod.keystore'
KS_PASS = 'twpmodpass'


def repack_obb():
    pack = GGPack(OBB)
    existing = {k.lower() for k in pack.entries}
    w = GGPackWriter(OBB)
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
    print(f'adding {added} entries')
    os.makedirs('dist', exist_ok=True)
    w.write(OUT_OBB)
    pk = GGPack(OUT_OBB)
    print('final entries:', len(pk.entries))
    s = pk.read('bankmanager_20204_de.ogg')
    print('sample de:', s[:4], len(s))
    s = pk.read('bankmanager_20204_es.ogg')
    print('sample es:', s[:4], len(s))
    s = pk.read('ThimbleweedText_de.tsv')
    print('original intact:', s[:4])


def make_keystore():
    if not os.path.exists(KS):
        subprocess.run(['keytool', '-genkeypair', '-v', '-keystore', KS,
                        '-alias', 'twpmod', '-keyalg', 'RSA', '-keysize', '2048',
                        '-validity', '10000', '-storepass', KS_PASS,
                        '-keypass', KS_PASS, '-dname', 'CN=TWP Language Mod'],
                       check=True, capture_output=True)


def repack_apk():
    obb_path = OUT_OBB
    assert os.path.exists(obb_path), 'build the obb first'
    build = 'apk_build'
    if os.path.exists(build):
        shutil.rmtree(build)
    os.makedirs(build)
    with zipfile.ZipFile(SRC_APK) as z:
        names = [n for n in z.namelist() if not n.startswith('META-INF/')]
        for n in names:
            z.extract(n, build)
    # patched arm64 lib
    shutil.copyfile(PATCHED_SO, f'{build}/lib/arm64-v8a/libThimbleweedPark.so')
    # replace embedded obb with modded one
    shutil.copyfile(obb_path, f'{build}/assets/obb')
    # re-zip
    for p in (OUT_APK_UNSIGNED, OUT_APK_ALIGNED, OUT_APK):
        if os.path.exists(p):
            os.unlink(p)
    with zipfile.ZipFile(OUT_APK_UNSIGNED, 'w') as z:
        # AndroidManifest first (not required but conventional)
        z.write(f'{build}/AndroidManifest.xml', 'AndroidManifest.xml', zipfile.ZIP_STORED)
        for root, dirs, files in os.walk(build):
            for f in files:
                p = os.path.join(root, f)
                arc = os.path.relpath(p, build)
                if arc == 'AndroidManifest.xml':
                    continue
                if arc == 'assets/obb':
                    z.write(p, arc, compress_type=zipfile.ZIP_STORED)
                else:
                    z.write(p, arc, compress_type=zipfile.ZIP_DEFLATED)
    subprocess.run([f'{BT}/zipalign', '-f', '-p', '4', OUT_APK_UNSIGNED, OUT_APK_ALIGNED], check=True)
    make_keystore()
    subprocess.run([f'{BT}/apksigner', 'sign', '--ks', KS, '--ks-pass', f'pass:{KS_PASS}',
                    '--key-pass', f'pass:{KS_PASS}', '--out', OUT_APK, OUT_APK_ALIGNED], check=True)
    r = subprocess.run([f'{BT}/apksigner', 'verify', '--print-certs', OUT_APK], capture_output=True, text=True)
    print(r.stdout)
    print('built', OUT_APK, os.path.getsize(OUT_APK) // (1 << 20), 'MB')


if __name__ == '__main__':
    if 'obb' in sys.argv:
        repack_obb()
    if 'apk' in sys.argv:
        repack_apk()
