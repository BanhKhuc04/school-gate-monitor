"""Webcam check script - 5 lines to verify camera works."""
import cv2

cap = cv2.VideoCapture(0)
ret, frame = cap.read()
if ret:
    cv2.imshow("Webcam Test - Press 'q' to quit", frame)
    cv2.waitKey(0)
else:
    print("ERROR: Cannot read from webcam")
cap.release()
cv2.destroyAllWindows()
