import fs from 'node:fs/promises';
import path from 'node:path';
import sharp from 'sharp';

const publicImagesDir = path.join(process.cwd(), 'public', 'images');
const avatarsDir = path.join(publicImagesDir, 'avatars');
const thumbsDir = path.join(publicImagesDir, 'avatar-full-thumbs');

const MAX_WIDTH = 384;
const WEBP_QUALITY = 82;

async function listImageFiles(dir: string) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isFile() && /\.(png|jpe?g|webp)$/i.test(entry.name))
    .map((entry) => entry.name);
}

async function fileExists(filePath: string) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  await fs.mkdir(thumbsDir, { recursive: true });

  const files = await listImageFiles(avatarsDir);
  let generated = 0;
  let skipped = 0;

  for (const filename of files) {
    const sourcePath = path.join(avatarsDir, filename);
    const outputPath = path.join(thumbsDir, filename.replace(/\.[^.]+$/, '.webp'));

    const [sourceStat, outputExists] = await Promise.all([
      fs.stat(sourcePath),
      fileExists(outputPath),
    ]);

    if (outputExists) {
      const outputStat = await fs.stat(outputPath);
      if (outputStat.mtimeMs >= sourceStat.mtimeMs) {
        skipped += 1;
        continue;
      }
    }

    await sharp(sourcePath)
      .rotate()
      .resize({ width: MAX_WIDTH, withoutEnlargement: true })
      .webp({ quality: WEBP_QUALITY })
      .toFile(outputPath);

    generated += 1;
  }

  console.log(`full avatar thumbnails: generated ${generated}, skipped ${skipped}, total ${files.length}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
