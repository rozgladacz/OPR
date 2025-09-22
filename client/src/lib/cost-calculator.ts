// OPR Cost Calculation Engine based on uploaded rules

// Quality modifiers
const QUALITY_MOD: Record<number, number> = {
  6: 0.8,
  5: 0.9,
  4: 1.0,
  3: 1.1,
  2: 1.2
};

// Defense modifiers (base)
const DEFENSE_BASE_MOD: Record<number, number> = {
  6: 0.8,
  5: 1.0,
  4: 1.33,
  3: 1.67,
  2: 2.0
};

// Defense modifiers with special rules
const DEFENSE_DELICATE_MOD: Record<number, number> = {
  6: 0.67,
  5: 0.9,
  4: 1.25,
  3: 1.6,
  2: 1.95
};

const DEFENSE_TOUGH_MOD: Record<number, number> = {
  6: 1.2,
  5: 1.3,
  4: 1.5,
  3: 1.8,
  2: 2.05
};

const DEFENSE_REGENERATION_MOD: Record<number, number> = {
  6: 1.2,
  5: 1.4,
  4: 1.8,
  3: 2.3,
  2: 3.0
};

// Toughness modifiers
const TOUGHNESS_MOD: Record<number, number> = {
  1: 1.0,
  2: 2.15,
  3: 3.5,
  6: 8.0,
  9: 13.0,
  12: 18.0
};

// Range modifiers for weapons
const RANGE_MOD: Record<string, number> = {
  "melee": 0.6,
  "12": 0.65,
  "18": 1.0,
  "24": 1.25,
  "30": 1.45,
  "36": 1.55
};

// AP modifiers
const AP_BASE_MOD: Record<number, number> = {
  [-1]: 0.8,
  0: 1.0,
  1: 1.5,
  2: 1.9,
  3: 2.25,
  4: 2.5,
  5: 2.65
};

// Special weapon ability modifiers
const WEAPON_MODIFIERS = {
  blast: (x: number) => {
    const blastMod: Record<number, number> = { 2: 1.95, 3: 2.8, 6: 4.3 };
    return blastMod[x] || 1.0;
  },
  deadly: (x: number) => {
    const deadlyMod: Record<number, number> = { 2: 1.9, 3: 2.6, 6: 3.8 };
    return deadlyMod[x] || 1.0;
  },
  indirect: 1.2,
  targeting: 1.1,
  oneUse: 0.4,
  overcharge: 1.4,
  reliable: 1.0, // Quality becomes 2+ in hit chance
  precise: 1.5,
  assault: 1.0, // Can be used in melee
  noRegen: 1.1
};

export function calculateBaseModelCost(
  quality: number, 
  defense: number, 
  toughness: number, 
  flags: Record<string, any> = {}
): number {
  const qualityMod = QUALITY_MOD[quality] || 1.0;
  
  let defenseMod = DEFENSE_BASE_MOD[defense] || 1.0;
  if (flags.delicate) defenseMod = DEFENSE_DELICATE_MOD[defense] || defenseMod;
  if (flags.tough) defenseMod = DEFENSE_TOUGH_MOD[defense] || defenseMod;
  if (flags.regeneration) defenseMod = DEFENSE_REGENERATION_MOD[defense] || defenseMod;
  
  const toughnessMod = TOUGHNESS_MOD[toughness] || Math.pow(toughness / 3, 1.5);
  
  return 5 * qualityMod * defenseMod * toughnessMod;
}

export function calculateWeaponCost(
  weapon: {
    range: string;
    attacks: number;
    ap: number;
    tags: string[];
  },
  unitQuality: number,
  unitFlags: Record<string, any> = {}
): number {
  const rangeMod = RANGE_MOD[weapon.range] || 1.0;
  
  // Hit chance calculation: 7 - quality
  let hitChance = Math.max(0.1, (7 - unitQuality) / 6);
  
  // Modify for special abilities
  if (weapon.tags.includes("reliable")) hitChance = Math.max(0.1, 5 / 6); // Quality 2+
  if (weapon.tags.includes("rending")) hitChance += 1/6;
  if (weapon.tags.includes("fury") || weapon.tags.includes("relentless")) hitChance += 0.65/6;
  if (weapon.tags.includes("impact")) hitChance += 0.65/6;
  if (weapon.tags.includes("targeting")) hitChance += 0.35/6;
  if (weapon.tags.includes("heavy")) hitChance -= 0.35/6;
  
  const apMod = AP_BASE_MOD[weapon.ap] || 1.0;
  
  // Apply special ability modifiers
  let abilityMod = 1.0;
  weapon.tags.forEach(tag => {
    if (tag.startsWith("blast(")) {
      const x = parseInt(tag.match(/\d+/)?.[0] || "2");
      abilityMod *= WEAPON_MODIFIERS.blast(x);
    } else if (tag.startsWith("deadly(")) {
      const x = parseInt(tag.match(/\d+/)?.[0] || "2");
      abilityMod *= WEAPON_MODIFIERS.deadly(x);
    } else if (tag === "indirect") {
      abilityMod *= WEAPON_MODIFIERS.indirect;
    } else if (tag === "targeting") {
      abilityMod *= WEAPON_MODIFIERS.targeting;
    } else if (tag === "oneUse") {
      abilityMod *= WEAPON_MODIFIERS.oneUse;
    } else if (tag === "overcharge") {
      abilityMod *= WEAPON_MODIFIERS.overcharge;
    } else if (tag === "precise") {
      abilityMod *= WEAPON_MODIFIERS.precise;
    } else if (tag === "noRegen") {
      abilityMod *= WEAPON_MODIFIERS.noRegen;
    }
  });
  
  return weapon.attacks * 2 * rangeMod * hitChance * apMod * abilityMod;
}

export function calculateAbilityCost(
  abilityName: string,
  toughness: number,
  params: Record<string, any> = {}
): number {
  const perToughnessCosts: Record<string, number> = {
    "ambush": 2,
    "scout": 2,
    "fast": 1,
    "slow": -1,
    "skirmisher": 1.5,
    "immobile": -2.5,
    "agile": 0.5,
    "clumsy": -0.5,
    "flying": 1,
    "aircraft": 3,
    "fury": 1, // Per weapon
    "relentless": 1, // Per weapon
    "goodShot": 1, // Per weapon
    "badShot": -1, // Per weapon
    "counter": 2,
    "delicate": 0, // See defense table
    "tough": 0, // See defense table
    "regeneration": 0, // See defense table
    "stealth": 2,
    "shield": 1.25,
    "entrenched": 1,
    "fearless": 0, // See quality table
    "reckless": 0, // See quality table
    "guardian": 3
  };
  
  const baseCost = perToughnessCosts[abilityName.toLowerCase()] || 0;
  return baseCost * toughness;
}

export function calculateUnitTotalCost(
  unit: {
    quality: number;
    defense: number;
    toughness: number;
    flags?: Record<string, any>;
  },
  weapon?: {
    range: string;
    attacks: number;
    ap: number;
    tags: string[];
  },
  abilities: string[] = [],
  count: number = 1
): number {
  const baseCost = calculateBaseModelCost(unit.quality, unit.defense, unit.toughness, unit.flags);
  
  let weaponCost = 0;
  if (weapon) {
    weaponCost = calculateWeaponCost(weapon, unit.quality, unit.flags);
  }
  
  let abilityCost = 0;
  abilities.forEach(ability => {
    abilityCost += calculateAbilityCost(ability, unit.toughness);
  });
  
  const totalCostPerModel = baseCost + weaponCost + abilityCost;
  return Math.round(totalCostPerModel * count);
}

export function calculateRosterTotalCost(
  units: Array<{
    unit: {
      quality: number;
      defense: number;
      toughness: number;
      flags?: Record<string, any>;
    };
    weapon?: {
      range: string;
      attacks: number;
      ap: number;
      tags: string[];
    };
    abilities?: string[];
    count: number;
  }>
): number {
  return units.reduce((total, unitEntry) => {
    return total + calculateUnitTotalCost(
      unitEntry.unit,
      unitEntry.weapon,
      unitEntry.abilities,
      unitEntry.count
    );
  }, 0);
}
