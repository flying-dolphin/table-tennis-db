import os
import cv2
import numpy as np
import glob

def crop_head_intelligent(image_path, output_path, face_cascade):
    # 读取图片 (处理包含中文路径的情况)
    img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        return False, "Failed to load"

    h, w = img.shape[:2]
    # 转换为灰度图供 OpenCV Haar Cascade 使用
    if img.shape[2] == 4:
        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(gray, 1.1, 5)

    if len(faces) == 0:
        # 兜底逻辑：如果没检测到人脸，默认截取顶部从 5% 开始的 45% 宽度正方形
        side = int(w * 0.5)
        x1 = (w - side) // 2
        y1 = int(h * 0.05)
        crop = img[y1:y1+side, x1:x1+side]
        cv2.imencode('.png', crop)[1].tofile(output_path)
        return True, "Fallback (No face)"

    # 选取面积最大的脸
    face = max(faces, key=lambda f: f[2] * f[3])
    fx, fy, fw, fh = face

    # 计算人脸中心
    cx = fx + fw // 2
    cy = fy + fh // 2

    # 计算头部的理想范围
    # Haar Cascade 的框通常比 MediaPipe 的小一点，倍数可以稍微大一点，取 2.2 - 2.8
    side = int(fw * 2.5)
    
    # 将中心稍微上移，因为头部重心在人脸框中心偏上
    cy_adjusted = cy - int(fh * 0.2)

    # 计算裁剪区域坐标
    x1 = cx - side // 2
    y1 = cy_adjusted - side // 2
    x2 = x1 + side
    y2 = y1 + side

    # 处理越界
    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > w:
        x1 -= (x2 - w)
        x2 = w
    if y2 > h:
        y1 -= (y2 - h)
        y2 = h
    
    # 再次检查越界并修正
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(w, x2)
    y2 = min(h, y2)

    crop = img[y1:y2, x1:x2]
    
    # 确保保存路径存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 保存结果
    cv2.imencode('.png', crop)[1].tofile(output_path)
    return True, "Success"

def main():
    input_dir = "web/public/images/avatars"
    output_dir = "web/public/images/crops"
    
    os.makedirs(output_dir, exist_ok=True)
    
    # 使用 OpenCV 自带的 Haar 级联分类器
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    
    if face_cascade.empty():
        print("Error: Could not load face cascade classifier.")
        return

    files = glob.glob(os.path.join(input_dir, "*.png"))
    print(f"Found {len(files)} avatars to process.")
    
    success_count = 0
    fallback_count = 0
    
    for i, fpath in enumerate(files):
        fname = os.path.basename(fpath)
        if i % 50 == 0:
            print(f"Processing {i}/{len(files)}: {fname}")
        out_path = os.path.join(output_dir, fname)
        
        success, msg = crop_head_intelligent(fpath, out_path, face_cascade)
        if success:
            success_count += 1
            if "Fallback" in msg:
                fallback_count += 1
        else:
            print(f"[Error] {fname}: {msg}")

    print(f"\nProcessing finished.")
    print(f"Total: {len(files)}")
    print(f"Success: {success_count} (including {fallback_count} fallbacks)")
    print(f"Results saved to {output_dir}")

if __name__ == "__main__":
    main()
