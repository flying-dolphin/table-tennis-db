const RANKING_THUMB_DIR = '/images/avatar-thumbs';
const DETAIL_THUMB_DIR = '/images/avatar-full-thumbs';
const DEFAULT_AVATAR_FILE = 'player_default.png';

export type AvatarSources = {
  primary: string;
  fallbacks: string[];
  default: string;
};

function toThumbFilename(filename: string) {
  return filename.replace(/\.[^.]+$/, '.webp');
}

function toThumbPath(dir: string, filename: string) {
  return `${dir}/${toThumbFilename(filename)}`;
}

function getDefaultSources(dir: string): AvatarSources {
  const defaultAvatar = toThumbPath(dir, DEFAULT_AVATAR_FILE);
  return {
    primary: defaultAvatar,
    fallbacks: [],
    default: defaultAvatar,
  };
}

export function getRankingAvatarSources(avatarFile: string | null | undefined): AvatarSources {
  if (!avatarFile) {
    return getDefaultSources(RANKING_THUMB_DIR);
  }

  return {
    primary: toThumbPath(RANKING_THUMB_DIR, avatarFile),
    fallbacks: [],
    default: toThumbPath(RANKING_THUMB_DIR, DEFAULT_AVATAR_FILE),
  };
}

export function getPlayerDetailAvatarSources(avatarFile: string | null | undefined): AvatarSources {
  if (!avatarFile) {
    return getDefaultSources(DETAIL_THUMB_DIR);
  }

  return {
    primary: toThumbPath(DETAIL_THUMB_DIR, avatarFile),
    fallbacks: [],
    default: toThumbPath(DETAIL_THUMB_DIR, DEFAULT_AVATAR_FILE),
  };
}

export const getAvatarSources = getRankingAvatarSources;
