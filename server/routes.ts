import type { Express } from "express";
import { createServer, type Server } from "http";
import { setupAuth } from "./auth";
import { storage } from "./storage";
import { insertArmySchema, insertUnitSchema, insertWeaponSchema, insertRosterSchema, insertRosterUnitSchema, updateUnitSchema, updateWeaponSchema } from "@shared/schema";

export async function registerRoutes(app: Express): Promise<Server> {
  // Initialize data on startup
  await storage.initializeData();

  // Setup authentication
  setupAuth(app);

  // Helper middleware to require authentication
  const requireAuth = (req: any, res: any, next: any) => {
    if (!req.isAuthenticated()) {
      return res.status(401).json({ message: "Authentication required" });
    }
    next();
  };

  // Armies routes
  app.get("/api/armies", async (req, res) => {
    try {
      const userId = req.user?.id;
      const armies = await storage.getArmies(userId);
      res.json(armies);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch armies" });
    }
  });

  app.get("/api/armies/:id", async (req, res) => {
    try {
      const army = await storage.getArmy(req.params.id);
      if (!army) {
        return res.status(404).json({ message: "Army not found" });
      }
      res.json(army);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch army" });
    }
  });

  app.post("/api/armies", requireAuth, async (req, res) => {
    try {
      const armyData = insertArmySchema.parse({
        ...req.body,
        ownerId: req.user?.id,
        rulesetId: req.body.rulesetId || "default"
      });
      const army = await storage.createArmy(armyData);
      res.status(201).json(army);
    } catch (error) {
      res.status(400).json({ message: "Invalid army data" });
    }
  });

  app.put("/api/armies/:id", requireAuth, async (req, res) => {
    try {
      const army = await storage.updateArmy(req.params.id, req.body);
      res.json(army);
    } catch (error) {
      res.status(500).json({ message: "Failed to update army" });
    }
  });

  app.delete("/api/armies/:id", requireAuth, async (req, res) => {
    try {
      await storage.deleteArmy(req.params.id);
      res.status(204).send();
    } catch (error) {
      res.status(500).json({ message: "Failed to delete army" });
    }
  });

  // Units routes
  app.get("/api/armies/:armyId/units", async (req, res) => {
    try {
      const units = await storage.getUnits(req.params.armyId);
      res.json(units);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch units" });
    }
  });

  app.post("/api/armies/:armyId/units", requireAuth, async (req, res) => {
    try {
      const unitData = insertUnitSchema.parse({
        ...req.body,
        armyId: req.params.armyId,
        ownerId: req.user?.id
      });
      const unit = await storage.createUnit(unitData);
      res.status(201).json(unit);
    } catch (error) {
      res.status(400).json({ message: "Invalid unit data" });
    }
  });

  app.put("/api/units/:id", requireAuth, async (req, res) => {
    try {
      const unit = await storage.updateUnit(req.params.id, req.body);
      res.json(unit);
    } catch (error) {
      res.status(500).json({ message: "Failed to update unit" });
    }
  });

  app.delete("/api/units/:id", requireAuth, async (req, res) => {
    try {
      await storage.deleteUnit(req.params.id);
      res.status(204).send();
    } catch (error) {
      res.status(500).json({ message: "Failed to delete unit" });
    }
  });

  // Weapons routes
  app.get("/api/weapons", async (req, res) => {
    try {
      const userId = req.user?.id;
      const weapons = await storage.getWeapons(userId);
      res.json(weapons);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch weapons" });
    }
  });

  app.post("/api/weapons", requireAuth, async (req, res) => {
    try {
      console.log("Weapon creation request body:", req.body);
      const weaponData = insertWeaponSchema.parse({
        ...req.body,
        ownerId: req.user?.id
      });
      console.log("Parsed weapon data:", weaponData);
      const weapon = await storage.createWeapon(weaponData);
      res.status(201).json(weapon);
    } catch (error) {
      console.error("Weapon creation error:", error);
      if (error.issues) {
        console.error("Zod validation issues:", error.issues);
        res.status(400).json({ 
          message: "Invalid weapon data", 
          details: error.issues.map((issue: any) => ({
            field: issue.path.join('.'),
            message: issue.message
          }))
        });
      } else {
        res.status(400).json({ message: "Invalid weapon data", error: error.message });
      }
    }
  });

  app.put("/api/weapons/:id", requireAuth, async (req, res) => {
    try {
      const weapon = await storage.updateWeapon(req.params.id, req.body);
      res.json(weapon);
    } catch (error) {
      res.status(500).json({ message: "Failed to update weapon" });
    }
  });

  app.delete("/api/weapons/:id", requireAuth, async (req, res) => {
    try {
      await storage.deleteWeapon(req.params.id);
      res.status(204).send();
    } catch (error) {
      res.status(500).json({ message: "Failed to delete weapon" });
    }
  });

  // Abilities routes
  app.get("/api/abilities", async (req, res) => {
    try {
      const userId = req.user?.id;
      const abilities = await storage.getAbilities(userId);
      res.json(abilities);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch abilities" });
    }
  });

  // Rosters routes
  app.get("/api/rosters", requireAuth, async (req, res) => {
    try {
      const rosters = await storage.getRosters(req.user?.id || '');
      res.json(rosters);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch rosters" });
    }
  });

  app.get("/api/rosters/:id", requireAuth, async (req, res) => {
    try {
      const roster = await storage.getRoster(req.params.id);
      if (!roster) {
        return res.status(404).json({ message: "Roster not found" });
      }
      res.json(roster);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch roster" });
    }
  });

  app.post("/api/rosters", requireAuth, async (req, res) => {
    try {
      const rosterData = insertRosterSchema.parse({
        ...req.body,
        ownerId: req.user?.id
      });
      const roster = await storage.createRoster(rosterData);
      res.status(201).json(roster);
    } catch (error) {
      res.status(400).json({ message: "Invalid roster data" });
    }
  });

  app.put("/api/rosters/:id", requireAuth, async (req, res) => {
    try {
      const roster = await storage.updateRoster(req.params.id, req.body);
      res.json(roster);
    } catch (error) {
      res.status(500).json({ message: "Failed to update roster" });
    }
  });

  app.delete("/api/rosters/:id", requireAuth, async (req, res) => {
    try {
      await storage.deleteRoster(req.params.id);
      res.status(204).send();
    } catch (error) {
      res.status(500).json({ message: "Failed to delete roster" });
    }
  });

  // Roster units routes
  app.get("/api/rosters/:rosterId/units", async (req, res) => {
    try {
      const rosterUnits = await storage.getRosterUnits(req.params.rosterId);
      res.json(rosterUnits);
    } catch (error) {
      res.status(500).json({ message: "Failed to fetch roster units" });
    }
  });

  app.post("/api/rosters/:rosterId/units", requireAuth, async (req, res) => {
    try {
      const rosterUnitData = insertRosterUnitSchema.parse({
        ...req.body,
        rosterId: req.params.rosterId
      });
      const rosterUnit = await storage.addRosterUnit(rosterUnitData);
      res.status(201).json(rosterUnit);
    } catch (error) {
      res.status(400).json({ message: "Invalid roster unit data" });
    }
  });

  app.put("/api/roster-units/:id", requireAuth, async (req, res) => {
    try {
      const rosterUnit = await storage.updateRosterUnit(req.params.id, req.body);
      res.json(rosterUnit);
    } catch (error) {
      res.status(500).json({ message: "Failed to update roster unit" });
    }
  });

  app.delete("/api/roster-units/:id", requireAuth, async (req, res) => {
    try {
      await storage.deleteRosterUnit(req.params.id);
      res.status(204).send();
    } catch (error) {
      res.status(500).json({ message: "Failed to delete roster unit" });
    }
  });

  const httpServer = createServer(app);
  return httpServer;
}
