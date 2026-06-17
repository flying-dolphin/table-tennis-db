import { readdirSync } from 'node:fs';
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
  return loadManifest().has(name) ? name : null;
}
