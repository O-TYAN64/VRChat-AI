import cv2
import numpy as np
import time
import ctypes
import win32gui
import win32ui
import win32con
import pytesseract

# ===============================
# Tesseract Ë®≠ÂÆöÔºàWindowsÔºâ
# ===============================
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

# ===============================
# VRChat „Ç¶„Ç£„É≥„Éâ„Ç¶Ê§úÁ¥¢
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
# VRChat „Ç¶„Ç£„É≥„Éâ„Ç¶„Ç≠„É£„Éó„ÉÅ„É£
# ===============================
def capture_window(hwnd):
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    w, h = right, bottom
    if w <= 0 or h <= 0:
        return None

    hwndDC = win32gui.GetWindowDC(hwnd)
    srcDC = win32ui.CreateDCFromHandle(hwndDC)
    memDC = srcDC.CreateCompatibleDC()

    bitmap = win32ui.CreateBitmap()
    bitmap.CreateCompatibleBitmap(srcDC, w, h)
    memDC.SelectObject(bitmap)

    ctypes.windll.user32.PrintWindow(hwnd, memDC.GetSafeHdc(), 2)

    buf = bitmap.GetBitmapBits(True)
    img = np.frombuffer(buf, dtype=np.uint8)
    img.shape = (h, w, 4)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    win32gui.DeleteObject(bitmap.GetHandle())
    memDC.DeleteDC()
    srcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    return img

# ===============================
# „Éç„Éº„É†„Éó„É¨„Éº„Éà„Åå„ÄåÈùí„ÅÑ„Åã„ÄçÂà§ÂÆö
# ===============================
def is_speaking(frame):
    h, w = frame.shape[:2]

    # „Éç„Éº„É†„Éó„É¨„Éº„ÉàÊû†ÈÉ®ÂàÜÔºà„Åä„Åä„Çà„ÅùÔºâ
    roi = frame[
        int(h * 0.06):int(h * 0.11),
        int(w * 0.35):int(w * 0.65)
    ]

    if roi.size == 0:
        return False

    b, g, r = np.mean(roi.reshape(-1, 3), axis=0)

    # ÈùíÂØÑ„Çä„Å™„ÇâÁô∫Ë©±‰∏≠
    return b > 140 and g > 100 and r < 120

# ===============================
# „Éç„Éº„É†„Éó„É¨„Éº„Éà„Åã„ÇâÂêçÂâç„Çí OCR
# ===============================
def extract_speaker_name(frame):
    h, w = frame.shape[:2]

    roi = frame[
        int(h * 0.11):int(h * 0.17),
        int(w * 0.35):int(w * 0.65)
    ]

    if roi.size == 0:
        return None

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2)
    _, th = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)

    text = pytesseract.image_to_string(
        th,
        lang="eng",
        config="--psm 7"
    )

    name = text.strip().split("\n")[0].replace(" ", "")
    return name if len(name) >= 2 else None

# ===============================
# „É°„Ç§„É≥
# ===============================
def main():
    print("üîç Searching VRChat window...")
    hwnd = find_vrchat_window()
    if not hwnd:
        print("‚ùå VRChat window not found")
        return

    print("‚úÖ VRChat window found")
    cv2.namedWindow("VRChat Speaker Observer", cv2.WINDOW_NORMAL)

    last_speaker = None

    while True:
        frame = capture_window(hwnd)
        if frame is None:
            time.sleep(0.1)
            continue

        speaking = is_speaking(frame)
        speaker = extract_speaker_name(frame)

        if speaking and speaker:
            cv2.putText(
                frame,
                f"SPEAKING: {speaker}",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (255, 200, 0),
                2
            )
            last_speaker = speaker
        else:
            last_speaker = None

        cv2.imshow("VRChat Speaker Observer", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(0.03)

    cv2.destroyAllWindows()