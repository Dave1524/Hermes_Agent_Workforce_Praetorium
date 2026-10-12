export const SCOPE_PATTERN = /^(vault:\S+|repo:[A-Za-z0-9._-]+)$/;

const VAULT_DIRS = [
  "00_system", "01_identity", "02_business", "03_projects", "04_operations", "05_knowledge",
  "06_resources", "07_daily", "08_skills", "09_investing", "10_archive", "11_entities",
];
const REPOS = ["agent-workforce", "Obsidian_AI_Operating_System", "energy-ledger", "AI_Trading_Bot", "Vantage_Consulting_Website"];

export const SCOPE_OPTIONS = [...VAULT_DIRS.map((d) => `vault:${d}`), ...REPOS.map((r) => `repo:${r}`)];

export const matchingScopes = (query: string, chosen: string[]): string[] => {
  const q = query.trim().toLowerCase();
  return SCOPE_OPTIONS.filter((o) => !chosen.includes(o) && o.toLowerCase().includes(q));
};
