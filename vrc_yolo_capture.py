import cv2
import numpy as np
import time
import ctypes
import win32gui
import win32ui
import win32con

from ultralytics import YOLO

# ===============================
# VRChat ウィンドウキャプチャ
# ===============================
def capture_window(hwnd):
    rect = win32gui.GetClientRect(hwnd)
    w, h = rect[2], rect[3]

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    result = ctypes.windll.user32.PrintWindow(
        hwnd, saveDC.GetSafeHdc(), 2
    )

    bmpstr = saveBitMap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8)
    img.shape = (h, w, 4)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    if result != 1:
        return None

    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

# ===============================
# VRChat ウィンドウ検索
# ===============================
def find_vrchat_window():
    def callback(hwnd, result):
        title = win32gui.GetWindowText(hwnd)
        if "VRChat" in title:
            result.append(hwnd)

    result = []
    win32gui.EnumWindows(callback, result)
    return result[0] if result else None

# ===============================
# オーバーレイ描画
# ===============================
def draw_overlay(img, results, fps):
    h, w, _ = img.shape

    boxes = results[0].boxes
    names = results[0].names

    detected_lines = []
    if boxes is not None:
        for box in boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            label = names.get(cls_id, str(cls_id))
            detected_lines.append(f"{label} ({conf:.2f})")

    # 背景
    overlay_height = 20 * (len(detected_lines) + 3)
    cv2.rectangle(
        img, (5, 5), (350, overlay_height),
        (0, 0, 0), -1
    )

    # テキスト
    y = 25
    cv2.putText(
        img, f"FPS: {fps:.1f}",
        (10, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6, (0, 255, 0), 2
    )
    y += 25

    cv2.putText(
        img, f"Detected: {len(detected_lines)}",
        (10, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6, (0, 255, 255), 2
    )
    y += 25

    for line in detected_lines:
        cv2.putText(
            img, line,
            (10, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55, (255, 255, 255), 1
        )
        y += 20

# ===============================
# メイン
# ===============================
def capture():
    print("🔍 VRChat window searching...")
    hwnd = find_vrchat_window()

    if hwnd is None:
        print("❌ VRChat window not found")
        return

    print("✅ VRChat window found")

    model = YOLO("pretrained.pt")

    prev_time = time.time()

    while True:
        frame = capture_window(hwnd)
        if frame is None:
            time.sleep(0.1)
            continue

        results = model(frame, conf=0.4, verbose=False)
        annotated = results[0].plot()

        # FPS計算
        now = time.time()
        fps = 1.0 / (now - prev_time)
        prev_time = now

        # オーバーレイ描画
        draw_overlay(annotated, results, fps)

        cv2.imshow("VRChat + YOLO", annotated)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(0.03)

    cv2.destroyAllWindows()