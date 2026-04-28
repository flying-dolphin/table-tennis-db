import { readdirSync } from 'node:fs';
import path from 'node:path';

const CROPS_DIR = path.join(process.cwd(), 'public', 'images', 'crops');

let manifest: Set<string> | null = null;

function loadManifest(): Set<string> {
  if (manifest) return manifest;
  try {
    const files = readdirSync(CROPS_DIR);
    manifest = new Set(files);
  } catch {
    manifest = new Set();
  }
  return manifest;
}

export function filterAvatarFile(name: string | null | undefined): string | null {
  if (!name) return null;
  return loadManifest().has(name) ? name : null;
}
