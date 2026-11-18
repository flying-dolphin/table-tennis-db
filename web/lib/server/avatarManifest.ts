import { existsSync, readdirSync } from 'node:fs';
import path from 'node:path';

const RANKING_THUMBS_DIR = path.join(process.cwd(), 'public', 'images', 'avatar-thumbs');

let manifest: Set<string> | null = null;

function loadManifest(): Set<string> {
  if (manifest) return manifest;
  try {
    const files = readdirSync(RANKING_THUMBS_DIR);
    manifest = new Set(files.map((file) => file.replace(/\.[^.]+$/, '.png')));
  } catch {
    manifest = new Set();
  }
  return manifest;
}

export function filterAvatarFile(name: string | null | undefined): string | null {
  if (!name) return null;
  const files = loadManifest();
  if (files.has(name)) return name;

  if (path.basename(name) !== name || !name.endsWith('.png')) return null;
  const thumbnail = path.join(RANKING_THUMBS_DIR, name.replace(/\.png$/, '.webp'));
  if (!existsSync(thumbnail)) return null;

  files.add(name);
  return name;
}
