import { sql } from "drizzle-orm";
import { pgTable, text, varchar, integer, decimal, boolean, timestamp, jsonb } from "drizzle-orm/pg-core";
import { relations } from "drizzle-orm";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const users = pgTable("users", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  username: text("username").notNull().unique(),
  password: text("password").notNull(),
  isAdmin: boolean("is_admin").default(false),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const rulesets = pgTable("rulesets", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  configJson: jsonb("config_json").default({}),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const abilities = pgTable("abilities", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  type: text("type").notNull(), // 'unit', 'weapon', 'aura', 'active'
  description: text("description").notNull(),
  costHint: decimal("cost_hint", { precision: 8, scale: 2 }),
  configJson: jsonb("config_json").default({}),
  ownerId: varchar("owner_id").references(() => users.id),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const weapons = pgTable("weapons", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  range: text("range").notNull(),
  attacks: decimal("attacks", { precision: 4, scale: 1 }).notNull(),
  ap: integer("ap").notNull().default(0),
  tags: text("tags").array().default([]),
  notes: text("notes"),
  parentId: varchar("parent_id"),
  ownerId: varchar("owner_id").references(() => users.id),
  armyId: varchar("army_id"),
  cachedCost: decimal("cached_cost", { precision: 8, scale: 2 }),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const armies = pgTable("armies", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  rulesetId: varchar("ruleset_id").references(() => rulesets.id).notNull(),
  parentId: varchar("parent_id"),
  ownerId: varchar("owner_id").references(() => users.id),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const units = pgTable("units", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  quality: integer("quality").notNull(),
  defense: integer("defense").notNull(),
  toughness: integer("toughness").notNull(),
  defaultWeaponId: varchar("default_weapon_id"),
  flags: jsonb("flags").default({}),
  parentId: varchar("parent_id"),
  armyId: varchar("army_id").references(() => armies.id).notNull(),
  ownerId: varchar("owner_id").references(() => users.id),
  cachedCost: decimal("cached_cost", { precision: 8, scale: 2 }),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const unitAbilities = pgTable("unit_abilities", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  unitId: varchar("unit_id").references(() => units.id).notNull(),
  abilityId: varchar("ability_id").references(() => abilities.id).notNull(),
  paramsJson: jsonb("params_json").default({}),
});

export const rosters = pgTable("rosters", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  name: text("name").notNull(),
  armyId: varchar("army_id").references(() => armies.id).notNull(),
  ownerId: varchar("owner_id").references(() => users.id).notNull(),
  pointsLimit: integer("points_limit"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const rosterUnits = pgTable("roster_units", {
  id: varchar("id").primaryKey().default(sql`gen_random_uuid()`),
  rosterId: varchar("roster_id").references(() => rosters.id).notNull(),
  unitId: varchar("unit_id").references(() => units.id).notNull(),
  count: integer("count").notNull().default(1),
  selectedWeaponId: varchar("selected_weapon_id").references(() => weapons.id),
  extraWeaponsJson: jsonb("extra_weapons_json").default([]),
  cachedCost: decimal("cached_cost", { precision: 8, scale: 2 }),
});

// Relations
export const usersRelations = relations(users, ({ many }) => ({
  armies: many(armies),
  weapons: many(weapons),
  abilities: many(abilities),
  rosters: many(rosters),
}));

export const armiesRelations = relations(armies, ({ one, many }) => ({
  owner: one(users, { fields: [armies.ownerId], references: [users.id] }),
  ruleset: one(rulesets, { fields: [armies.rulesetId], references: [rulesets.id] }),
  parent: one(armies, { fields: [armies.parentId], references: [armies.id] }),
  units: many(units),
  rosters: many(rosters),
}));

export const unitsRelations = relations(units, ({ one, many }) => ({
  army: one(armies, { fields: [units.armyId], references: [armies.id] }),
  owner: one(users, { fields: [units.ownerId], references: [users.id] }),
  defaultWeapon: one(weapons, { fields: [units.defaultWeaponId], references: [weapons.id] }),
  parent: one(units, { fields: [units.parentId], references: [units.id] }),
  abilities: many(unitAbilities),
  rosterUnits: many(rosterUnits),
}));

export const weaponsRelations = relations(weapons, ({ one, many }) => ({
  owner: one(users, { fields: [weapons.ownerId], references: [users.id] }),
  parent: one(weapons, { fields: [weapons.parentId], references: [weapons.id] }),
  units: many(units),
  rosterUnits: many(rosterUnits),
}));

export const abilitiesRelations = relations(abilities, ({ one, many }) => ({
  owner: one(users, { fields: [abilities.ownerId], references: [users.id] }),
  unitAbilities: many(unitAbilities),
}));

export const unitAbilitiesRelations = relations(unitAbilities, ({ one }) => ({
  unit: one(units, { fields: [unitAbilities.unitId], references: [units.id] }),
  ability: one(abilities, { fields: [unitAbilities.abilityId], references: [abilities.id] }),
}));

export const rostersRelations = relations(rosters, ({ one, many }) => ({
  army: one(armies, { fields: [rosters.armyId], references: [armies.id] }),
  owner: one(users, { fields: [rosters.ownerId], references: [users.id] }),
  units: many(rosterUnits),
}));

export const rosterUnitsRelations = relations(rosterUnits, ({ one }) => ({
  roster: one(rosters, { fields: [rosterUnits.rosterId], references: [rosters.id] }),
  unit: one(units, { fields: [rosterUnits.unitId], references: [units.id] }),
  selectedWeapon: one(weapons, { fields: [rosterUnits.selectedWeaponId], references: [weapons.id] }),
}));

// Schemas
export const insertUserSchema = createInsertSchema(users).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertArmySchema = createInsertSchema(armies).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertUnitSchema = createInsertSchema(units).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
}).extend({
  cachedCost: decimalField().optional(),
});

export const updateUnitSchema = insertUnitSchema.partial();

export const insertWeaponSchema = createInsertSchema(weapons).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
}).extend({
  attacks: decimalField(),
  cachedCost: decimalField().optional(),
});

export const updateWeaponSchema = insertWeaponSchema.partial();

export const insertAbilitySchema = createInsertSchema(abilities).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
}).extend({
  costHint: decimalField().optional(),
});

export const updateAbilitySchema = insertAbilitySchema.partial();

export const insertRosterSchema = createInsertSchema(rosters).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});

export const insertRosterUnitSchema = createInsertSchema(rosterUnits).omit({
  id: true,
});

// Types
export type User = typeof users.$inferSelect;
export type InsertUser = z.infer<typeof insertUserSchema>;
export type Army = typeof armies.$inferSelect;
export type InsertArmy = z.infer<typeof insertArmySchema>;
export type Unit = typeof units.$inferSelect;
export type InsertUnit = z.infer<typeof insertUnitSchema>;
export type Weapon = typeof weapons.$inferSelect;
export type InsertWeapon = z.infer<typeof insertWeaponSchema>;
export type Ability = typeof abilities.$inferSelect;
export type InsertAbility = z.infer<typeof insertAbilitySchema>;
export type Roster = typeof rosters.$inferSelect;
export type InsertRoster = z.infer<typeof insertRosterSchema>;
export type RosterUnit = typeof rosterUnits.$inferSelect;
export type InsertRosterUnit = z.infer<typeof insertRosterUnitSchema>;
