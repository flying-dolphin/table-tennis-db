type RewriteRule = {
  canonical: string;
  aliases: string[];
};

const EVENT_REWRITE_RULES: RewriteRule[] = [
  {
    canonical: "混合团体",
    aliases: ["混团"],
  },
  {
    canonical: "世界乒乓球锦标赛",
    aliases: ["世乒赛", "世锦赛"],
  },
  {
    canonical: "亚洲锦标赛",
    aliases: ["亚锦赛"],
  },
  {
    canonical: "亚洲团体锦标赛",
    aliases: ["亚锦赛"],
  },
];

export function normalizeQuery(query: string) {
  return query.trim().toLowerCase().replace(/\s+/g, " ");
}

export function expandEventQuery(query: string) {
  const normalizedQuery = normalizeQuery(query);
  if (!normalizedQuery) return [];

  const expanded = new Set<string>([normalizedQuery]);

  for (const rule of EVENT_REWRITE_RULES) {
    const canonical = normalizeQuery(rule.canonical);
    const aliases = rule.aliases.map(normalizeQuery);

    if (aliases.includes(normalizedQuery)) {
      expanded.add(canonical);
      continue;
    }

    for (const alias of aliases) {
      if (!normalizedQuery.includes(alias)) continue;
      expanded.add(normalizedQuery.replaceAll(alias, canonical));
    }
  }

  return Array.from(expanded);
}
