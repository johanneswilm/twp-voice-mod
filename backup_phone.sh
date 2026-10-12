#!/bin/bash
# Back up the installed Thimbleweed Park from a connected Android phone:
# APK(s), OBB(s), and savegames. Run with the phone plugged in and
# USB debugging enabled.
set -u
PKG=com.terribletoybox.thimbleweedparkandroid
OUT=phone_backup_$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUT"

echo "== device check =="
adb devices | tail -n +2 | grep -q device$ || { echo "NO DEVICE connected (enable USB debugging, check the phone screen for the authorization prompt)"; exit 1; }

echo "== package info =="
adb shell dumpsys package $PKG > "$OUT/package_info.txt" 2>/dev/null
grep -E "versionName|versionCode" "$OUT/package_info.txt" | head -4

echo "== pulling APK(s) =="
i=0
for p in $(adb shell pm path $PKG | sed 's/package://'); do
    i=$((i+1))
    name=$(basename "$p")
    echo "  pull $p"
    adb pull "$p" "$OUT/$name" || echo "  FAILED: $p"
done

echo "== pulling OBB(s) =="
adb shell "ls /storage/emulated/0/Android/obb/$PKG/ 2>/dev/null" > "$OUT/obb_list.txt"
cat "$OUT/obb_list.txt"
while read -r f; do
    [ -n "$f" ] || continue
    echo "  pull $f"
    adb pull "/storage/emulated/0/Android/obb/$PKG/$f" "$OUT/$f" || echo "  FAILED: $f"
done < "$OUT/obb_list.txt"

echo "== pulling savegames (Android/data) =="
adb pull "/storage/emulated/0/Android/data/$PKG" "$OUT/data_files" 2>&1 | tail -2

echo "== summary =="
ls -la "$OUT"
echo
echo "backup saved in: $OUT"
