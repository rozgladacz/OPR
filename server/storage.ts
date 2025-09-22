import { 
  users, armies, units, weapons, abilities, rosters, rosterUnits, unitAbilities, rulesets,
  type User, type InsertUser, type Army, type InsertArmy, type Unit, type InsertUnit,
  type Weapon, type InsertWeapon, type Ability, type InsertAbility, type Roster,
  type InsertRoster, type RosterUnit, type InsertRosterUnit
} from "@shared/schema";
import { db } from "./db";
import { eq, and, or, isNull } from "drizzle-orm";

export interface IStorage {
  // Users
  getUser(id: string): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;

  // Armies
  getArmies(userId?: string): Promise<Army[]>;
  getArmy(id: string): Promise<Army | undefined>;
  createArmy(army: InsertArmy): Promise<Army>;
  updateArmy(id: string, army: Partial<InsertArmy>): Promise<Army>;
  deleteArmy(id: string): Promise<void>;

  // Units
  getUnits(armyId: string): Promise<Unit[]>;
  getUnit(id: string): Promise<Unit | undefined>;
  createUnit(unit: InsertUnit): Promise<Unit>;
  updateUnit(id: string, unit: Partial<InsertUnit>): Promise<Unit>;
  deleteUnit(id: string): Promise<void>;

  // Weapons
  getWeapons(userId?: string): Promise<Weapon[]>;
  getWeapon(id: string): Promise<Weapon | undefined>;
  createWeapon(weapon: InsertWeapon): Promise<Weapon>;
  updateWeapon(id: string, weapon: Partial<InsertWeapon>): Promise<Weapon>;
  deleteWeapon(id: string): Promise<void>;

  // Abilities
  getAbilities(userId?: string): Promise<Ability[]>;
  createAbility(ability: InsertAbility): Promise<Ability>;

  // Rosters
  getRosters(userId: string): Promise<Roster[]>;
  getRoster(id: string): Promise<Roster | undefined>;
  createRoster(roster: InsertRoster): Promise<Roster>;
  updateRoster(id: string, roster: Partial<InsertRoster>): Promise<Roster>;
  deleteRoster(id: string): Promise<void>;

  // Roster Units
  getRosterUnits(rosterId: string): Promise<RosterUnit[]>;
  addRosterUnit(rosterUnit: InsertRosterUnit): Promise<RosterUnit>;
  updateRosterUnit(id: string, rosterUnit: Partial<InsertRosterUnit>): Promise<RosterUnit>;
  deleteRosterUnit(id: string): Promise<void>;

  // Initialize data
  initializeData(): Promise<void>;
}

export class DatabaseStorage implements IStorage {
  async getUser(id: string): Promise<User | undefined> {
    const [user] = await db.select().from(users).where(eq(users.id, id));
    return user || undefined;
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    const [user] = await db.select().from(users).where(eq(users.username, username));
    return user || undefined;
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const [user] = await db
      .insert(users)
      .values(insertUser)
      .returning();
    return user;
  }

  async getArmies(userId?: string): Promise<Army[]> {
    if (userId) {
      return await db.select().from(armies).where(
        or(eq(armies.ownerId, userId), isNull(armies.ownerId))
      ) as Army[];
    }
    return await db.select().from(armies).where(isNull(armies.ownerId)) as Army[];
  }

  async getArmy(id: string): Promise<Army | undefined> {
    const [army] = await db.select().from(armies).where(eq(armies.id, id));
    return army || undefined;
  }

  async createArmy(army: InsertArmy): Promise<Army> {
    const [newArmy] = await db.insert(armies).values(army).returning();
    return newArmy;
  }

  async updateArmy(id: string, army: Partial<InsertArmy>): Promise<Army> {
    const [updated] = await db.update(armies).set(army).where(eq(armies.id, id)).returning();
    return updated;
  }

  async deleteArmy(id: string): Promise<void> {
    await db.delete(armies).where(eq(armies.id, id));
  }

  async getUnits(armyId: string): Promise<Unit[]> {
    return await db.select().from(units).where(eq(units.armyId, armyId)) as Unit[];
  }

  async getUnit(id: string): Promise<Unit | undefined> {
    const [unit] = await db.select().from(units).where(eq(units.id, id));
    return unit || undefined;
  }

  async createUnit(unit: InsertUnit): Promise<Unit> {
    const [newUnit] = await db.insert(units).values(unit).returning();
    return newUnit as Unit;
  }

  async updateUnit(id: string, unit: Partial<InsertUnit>): Promise<Unit> {
    const [updated] = await db.update(units).set(unit).where(eq(units.id, id)).returning();
    return updated;
  }

  async deleteUnit(id: string): Promise<void> {
    await db.delete(units).where(eq(units.id, id));
  }

  async getWeapons(userId?: string): Promise<Weapon[]> {
    if (userId) {
      return await db.select().from(weapons).where(
        or(eq(weapons.ownerId, userId), isNull(weapons.ownerId))
      );
    }
    return await db.select().from(weapons).where(isNull(weapons.ownerId));
  }

  async getWeapon(id: string): Promise<Weapon | undefined> {
    const [weapon] = await db.select().from(weapons).where(eq(weapons.id, id));
    return weapon || undefined;
  }

  async createWeapon(weapon: InsertWeapon): Promise<Weapon> {
    const [newWeapon] = await db.insert(weapons).values(weapon).returning();
    return newWeapon;
  }

  async updateWeapon(id: string, weapon: Partial<InsertWeapon>): Promise<Weapon> {
    const [updated] = await db.update(weapons).set(weapon).where(eq(weapons.id, id)).returning();
    return updated;
  }

  async deleteWeapon(id: string): Promise<void> {
    await db.delete(weapons).where(eq(weapons.id, id));
  }

  async getAbilities(userId?: string): Promise<Ability[]> {
    if (userId) {
      return await db.select().from(abilities).where(
        or(eq(abilities.ownerId, userId), isNull(abilities.ownerId))
      );
    }
    return await db.select().from(abilities).where(isNull(abilities.ownerId));
  }

  async createAbility(ability: InsertAbility): Promise<Ability> {
    const [newAbility] = await db.insert(abilities).values(ability).returning();
    return newAbility;
  }

  async getRosters(userId: string): Promise<Roster[]> {
    return await db.select().from(rosters).where(eq(rosters.ownerId, userId));
  }

  async getRoster(id: string): Promise<Roster | undefined> {
    const [roster] = await db.select().from(rosters).where(eq(rosters.id, id));
    return roster || undefined;
  }

  async createRoster(roster: InsertRoster): Promise<Roster> {
    const [newRoster] = await db.insert(rosters).values(roster).returning();
    return newRoster;
  }

  async updateRoster(id: string, roster: Partial<InsertRoster>): Promise<Roster> {
    const [updated] = await db.update(rosters).set(roster).where(eq(rosters.id, id)).returning();
    return updated;
  }

  async deleteRoster(id: string): Promise<void> {
    await db.delete(rosters).where(eq(rosters.id, id));
  }

  async getRosterUnits(rosterId: string): Promise<RosterUnit[]> {
    return await db.select().from(rosterUnits).where(eq(rosterUnits.rosterId, rosterId));
  }

  async addRosterUnit(rosterUnit: InsertRosterUnit): Promise<RosterUnit> {
    const [newRosterUnit] = await db.insert(rosterUnits).values(rosterUnit).returning();
    return newRosterUnit;
  }

  async updateRosterUnit(id: string, rosterUnit: Partial<InsertRosterUnit>): Promise<RosterUnit> {
    const [updated] = await db.update(rosterUnits).set(rosterUnit).where(eq(rosterUnits.id, id)).returning();
    return updated;
  }

  async deleteRosterUnit(id: string): Promise<void> {
    await db.delete(rosterUnits).where(eq(rosterUnits.id, id));
  }

  async initializeData(): Promise<void> {
    // Create default ruleset
    const [ruleset] = await db.insert(rulesets).values({
      name: "Default OPR Rules"
    }).onConflictDoNothing().returning();

    // Create sample weapons
    const sampleWeapons = [
      { name: "Lasgun", range: "24", attacks: 2, ap: 0, tags: ["Reliable"], notes: "Standard infantry weapon" },
      { name: "Battle Cannon", range: "48", attacks: 1, ap: 4, tags: ["Deadly(3)"], notes: "Tank main gun" },
      { name: "Heavy Bolter", range: "36", attacks: 3, ap: 1, tags: [], notes: "Heavy support weapon" },
      { name: "Chainsword", range: "melee", attacks: 2, ap: 0, tags: ["Assault"], notes: "Close combat weapon" },
      { name: "Plasma Gun", range: "24", attacks: 1, ap: 2, tags: ["Deadly(2)"], notes: "Advanced energy weapon" }
    ];

    for (const weapon of sampleWeapons) {
      await db.insert(weapons).values(weapon).onConflictDoNothing();
    }

    // Create sample abilities
    const sampleAbilities = [
      { name: "Flying", type: "unit", description: "Ignores terrain and units during movement", costHint: "1.0" },
      { name: "Fast", type: "unit", description: "Move +2\"", costHint: "1.0" },
      { name: "Tough(3)", type: "unit", description: "Ignore first 3 wounds", costHint: "2.0" },
      { name: "Scout", type: "unit", description: "Deploy after all other units", costHint: "2.0" },
      { name: "Regeneration", type: "unit", description: "Natural 6 on defense ignores next wound", costHint: "1.5" }
    ];

    for (const ability of sampleAbilities) {
      await db.insert(abilities).values(ability).onConflictDoNothing();
    }
  }
}

export const storage = new DatabaseStorage();
