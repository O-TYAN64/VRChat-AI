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

    if w <= 0 or h <= 0:
        return None

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

    if result != 1:
        saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con.SRCCOPY)

    bmpstr = saveBitMap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8)

    try:
        img.shape = (h, w, 4)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        img = None

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    return img

# ===============================
# VRChat ウィンドウ検索
# ===============================
def find_vrchat_window():
    result = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return

        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)

        if title == "VRChat" and class_name == "UnityWndClass":
            result.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return result[0] if result else None

# ===============================
# デバッグオーバーレイ
# ===============================
def draw_debug_overlay(img, detections, names, fps):
    lines = []
    for box in detections:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        label = names.get(cls_id, str(cls_id))
        lines.append(f"{label}: {conf:.2f}")

    h = 25 * (len(lines) + 3)
    cv2.rectangle(img, (5, 5), (360, h), (0, 0, 0), -1)

    y = 28
    cv2.putText(img, f"FPS: {fps:.1f}", (10, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    y += 23

    if lines:
        cv2.putText(img, f"Detections: {len(lines)}", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        y += 23
        for line in lines:
            cv2.putText(img, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            y += 18
    else:
        cv2.putText(img, "NO DETECTION", (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

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

    model = YOLO("base.pt")
    prev_time = time.time()

    cv2.namedWindow("VRChat + YOLO DEBUG", cv2.WINDOW_NORMAL)

    while True:
        frame = capture_window(hwnd)
        if frame is None:
            time.sleep(0.1)
            continue

        results = model(frame, conf=0.4, verbose=False)
        boxes = results[0].boxes
        names = results[0].names

        # FPS
        now = time.time()
        fps = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        # BBox描画（明示的）
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        draw_debug_overlay(frame, boxes or [], names, fps)

        cv2.imshow("VRChat + YOLO DEBUG", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(0.03)

    cv2.destroyAllWindows()