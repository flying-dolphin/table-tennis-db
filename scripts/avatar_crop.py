import argparse
import os

import cv2
import numpy as np


def _read_image(image_path: str):
    return cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)


def _mkdir(path: str):
    if not os.path.exists(path):
        os.makedirs(path)


def _clip01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _dedup_candidates(candidates):
    """按中心点和半径做轻量去重。"""
    out = []
    for c in sorted(candidates, key=lambda x: x["conf"], reverse=True):
        keep = True
        for k in out:
            close_xy = abs(c["x"] - k["x"]) <= 10 and abs(c["y"] - k["y"]) <= 10
            close_r = abs(c["r"] - k["r"]) <= 8
            if close_xy and close_r:
                keep = False
                break
        if keep:
            out.append(c)
    return out


def _collect_mask_candidates(row_bgr, y_offset, x0):
    row_h, row_w = row_bgr.shape[:2]
    hsv = cv2.cvtColor(row_bgr, cv2.COLOR_BGR2HSV)

    # 头像框浅蓝/浅白蓝区域。
    mask_blue = cv2.inRange(
        hsv,
        np.array([70, 5, 110], dtype=np.uint8),
        np.array([140, 190, 255], dtype=np.uint8),
    )
    mask_light = cv2.inRange(
        hsv,
        np.array([0, 0, 180], dtype=np.uint8),
        np.array([179, 70, 255], dtype=np.uint8),
    )
    mask = cv2.bitwise_or(mask_blue, mask_light)

    k = max(3, int(row_h * 0.02) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        area = cv2.contourArea(c)
        if area < row_h * row_w * 0.002:
            continue
        perimeter = cv2.arcLength(c, True)
        if perimeter <= 1:
            continue
        circularity = 4.0 * np.pi * area / (perimeter * perimeter)
        if circularity < 0.62:
            continue

        (cx, cy), radius = cv2.minEnclosingCircle(c)
        if radius < row_h * 0.12 or radius > row_h * 0.36:
            continue

        # 基础置信度：面积占比 + 圆度 + 横向先验 + 纵向先验（头像不应贴行边界）。
        area_ratio = area / max(1.0, row_h * row_w * 0.08)
        circ_score = _clip01((circularity - 0.60) / 0.40)
        x_center_prior = row_w * 0.52
        x_score = _clip01(1.0 - abs(cx - x_center_prior) / (row_w * 0.45))
        y_score = _clip01(1.0 - abs(cy - row_h * 0.52) / (row_h * 0.40))
        if cy < row_h * 0.18 or cy > row_h * 0.86:
            continue
        conf = _clip01(
            0.32 * _clip01(area_ratio) + 0.28 * circ_score + 0.18 * x_score + 0.22 * y_score
        )

        candidates.append(
            {
                "x": int(x0 + cx),
                "y": int(y_offset + cy),
                "r": int(radius),
                "conf": conf,
                "method": "mask",
            }
        )
    return _dedup_candidates(candidates)


def _collect_hough_candidates(row_bgr, y_offset, x0, row_h):
    gray = cv2.cvtColor(row_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.GaussianBlur(gray, (9, 9), 1.5)
    min_r = max(20, int(row_h * 0.12))
    max_r = max(min_r + 1, int(row_h * 0.36))

    out = []
    for param2 in (42, 36, 30, 26, 22):
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(30, int(row_h * 0.40)),
            param1=120,
            param2=param2,
            minRadius=min_r,
            maxRadius=max_r,
        )
        if circles is None:
            continue

        for cx, cy, r in np.around(circles[0]).astype(int):
            # 直接剔除贴近行顶部/底部的误检圆（第3行错误即此类）。
            if cy < row_h * 0.18 or cy > row_h * 0.86:
                continue
            x_score = _clip01(1.0 - abs(cx - row_bgr.shape[1] * 0.52) / (row_bgr.shape[1] * 0.45))
            y_score = _clip01(1.0 - abs(cy - row_h * 0.52) / (row_h * 0.35))
            r_target = row_h * 0.28
            r_score = _clip01(1.0 - abs(r - r_target) / max(1.0, row_h * 0.16))
            conf = _clip01(0.34 * x_score + 0.42 * y_score + 0.24 * r_score)

            out.append(
                {
                    "x": int(x0 + cx),
                    "y": int(y_offset + cy),
                    "r": int(r),
                    "conf": conf,
                    "method": "hough",
                }
            )
    return _dedup_candidates(out)


def _crop_square(img, x, y, r, padding_ratio=0.12):
    pad = int(r * padding_ratio)
    side = r + pad
    y1, y2 = max(0, y - side), min(img.shape[0], y + side)
    x1, x2 = max(0, x - side), min(img.shape[1], x + side)
    return img[y1:y2, x1:x2]


def _geom_consistency_score(x, r, x_med, r_med, width):
    """跨行几何一致性，用于只修正离群行（如第3行误选）。"""
    x_score = _clip01(1.0 - abs(x - x_med) / max(1.0, width * 0.09))
    r_score = _clip01(1.0 - abs(r - r_med) / max(1.0, r_med * 0.32))
    return 0.7 * x_score + 0.3 * r_score


def crop_avatars(image_path, output_dir="cropped_avatars", expected_count=5):
    img = _read_image(image_path)
    if img is None:
        raise RuntimeError(f"无法读取图片: {image_path}")

    _mkdir(output_dir)

    h, w = img.shape[:2]
    row_h = h // expected_count
    x0 = int(w * 0.10)
    x1 = int(w * 0.78)

    rows = []
    prelim = []
    for i in range(expected_count):
        y_start = i * row_h
        y_end = h if i == expected_count - 1 else (i + 1) * row_h
        roi = img[y_start:y_end, x0:x1]

        cands = []
        cands.extend(_collect_mask_candidates(roi, y_start, x0))
        cands.extend(_collect_hough_candidates(roi, y_start, x0, roi.shape[0]))
        cands = _dedup_candidates(cands)

        if not cands:
            print(f"[warn] 第 {i + 1} 行未检测到头像圆。")
            rows.append((i + 1, []))
            continue

        p = max(cands, key=lambda c: c["conf"])
        prelim.append(p)
        rows.append((i + 1, cands))

    if not prelim:
        raise RuntimeError("未检测到任何头像圆，请检查图像样式或调整阈值。")

    x_med = float(np.median(np.array([c["x"] for c in prelim], dtype=np.float32)))
    r_med = float(np.median(np.array([c["r"] for c in prelim], dtype=np.float32)))

    final_results = []
    for idx, cands in rows:
        if not cands:
            continue
        scored = []
        for c in cands:
            geom = _geom_consistency_score(c["x"], c["r"], x_med, r_med, w)
            final_score = 0.42 * c["conf"] + 0.58 * geom
            scored.append((final_score, c, geom))
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best, geom = scored[0]
        final_results.append((idx, best["x"], best["y"], best["r"], best["method"], best["conf"], geom, best_score))

    # 半径一致性修正：中心已对但半径异常时，收敛到全局中位半径。
    final_rs = np.array([it[3] for it in final_results], dtype=np.float32)
    if len(final_rs) >= 3:
        r_final_med = float(np.median(final_rs))
        adjusted = []
        for idx, x, y, r, method, conf, geom, s in final_results:
            if abs(r - r_final_med) > max(16.0, r_final_med * 0.22):
                print(
                    f"[radius_fix] 第 {idx} 行半径修正: r={r} -> {int(round(r_final_med))} "
                    f"(geom={geom:.3f})"
                )
                r = int(round(r_final_med))
            adjusted.append((idx, x, y, r, method, conf, geom, s))
        final_results = adjusted

    final_results.sort(key=lambda item: item[0])
    print(f"检测完成：{len(final_results)} / {expected_count}")

    for idx, x, y, r, method, conf, geom, s in final_results:
        avatar = _crop_square(img, x, y, r, padding_ratio=0.12)
        save_path = os.path.join(output_dir, f"avatar_{idx}.png")
        cv2.imwrite(save_path, avatar)
        print(
            f"[{method}] 已保存: {save_path} "
            f"(center=({x},{y}), r={r}, conf={conf:.3f}, geom={geom:.3f}, score={s:.3f})"
        )


def main():
    parser = argparse.ArgumentParser(description="按行识别并裁剪头像圆")
    parser.add_argument("image_path", help="输入大图路径")
    parser.add_argument("--output-dir", default="cropped_avatars", help="输出目录")
    parser.add_argument("--count", type=int, default=5, help="期望检测行数")
    args = parser.parse_args()

    crop_avatars(args.image_path, output_dir=args.output_dir, expected_count=args.count)


if __name__ == "__main__":
    main()
