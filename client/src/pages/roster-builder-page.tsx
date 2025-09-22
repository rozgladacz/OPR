import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRoute, Link } from "wouter";
import { Navbar } from "@/components/navbar";
import { UnitCard } from "@/components/unit-card";
import { CostCalculator } from "@/components/cost-calculator";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Plus, Minus, X, Printer, FileDown } from "lucide-react";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";
import { calculateUnitTotalCost } from "@/lib/cost-calculator";

export default function RosterBuilderPage() {
  const [, params] = useRoute("/rosters/:id/build");
  const rosterId = params?.id;
  const { toast } = useToast();

  const [pointsLimit, setPointsLimit] = useState<number>(2000);

  const { data: roster, isLoading: rosterLoading } = useQuery({
    queryKey: ["/api/rosters", rosterId],
    enabled: !!rosterId
  });

  const { data: rosterUnits, isLoading: rosterUnitsLoading } = useQuery({
    queryKey: ["/api/rosters", rosterId, "units"],
    enabled: !!rosterId
  });

  const { data: availableUnits, isLoading: unitsLoading } = useQuery({
    queryKey: ["/api/armies", roster?.armyId, "units"],
    enabled: !!roster?.armyId
  });

  const { data: weapons } = useQuery({
    queryKey: ["/api/weapons"]
  });

  const addUnitMutation = useMutation({
    mutationFn: async (unitData: { unitId: string; count: number }) => {
      const res = await apiRequest("POST", `/api/rosters/${rosterId}/units`, unitData);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/rosters", rosterId, "units"] });
      toast({
        title: "Unit added",
        description: "Unit has been added to your roster.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to add unit",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const updateRosterUnitMutation = useMutation({
    mutationFn: async ({ rosterUnitId, updates }: { rosterUnitId: string; updates: any }) => {
      const res = await apiRequest("PUT", `/api/roster-units/${rosterUnitId}`, updates);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/rosters", rosterId, "units"] });
    },
    onError: (error) => {
      toast({
        title: "Failed to update unit",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const removeRosterUnitMutation = useMutation({
    mutationFn: async (rosterUnitId: string) => {
      await apiRequest("DELETE", `/api/roster-units/${rosterUnitId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/rosters", rosterId, "units"] });
      toast({
        title: "Unit removed",
        description: "Unit has been removed from your roster.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to remove unit",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const updateRosterMutation = useMutation({
    mutationFn: async (updates: { pointsLimit: number }) => {
      const res = await apiRequest("PUT", `/api/rosters/${rosterId}`, updates);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/rosters", rosterId] });
    },
  });

  useEffect(() => {
    if (roster?.pointsLimit) {
      setPointsLimit(roster.pointsLimit);
    }
  }, [roster]);

  const handleAddUnit = (unitId: string) => {
    addUnitMutation.mutate({ unitId, count: 1 });
  };

  const handleUpdateCount = (rosterUnitId: string, newCount: number) => {
    if (newCount > 0) {
      updateRosterUnitMutation.mutate({
        rosterUnitId,
        updates: { count: newCount }
      });
    }
  };

  const handleUpdateWeapon = (rosterUnitId: string, weaponId: string) => {
    updateRosterUnitMutation.mutate({
      rosterUnitId,
      updates: { selectedWeaponId: weaponId || null }
    });
  };

  const handleRemoveUnit = (rosterUnitId: string) => {
    removeRosterUnitMutation.mutate(rosterUnitId);
  };

  const handleUpdatePointsLimit = () => {
    updateRosterMutation.mutate({ pointsLimit });
  };

  // Calculate total costs
  const calculateTotalCosts = () => {
    if (!rosterUnits || !availableUnits || !weapons) {
      return { unitsCost: 0, weaponsCost: 0, abilitiesCost: 0, totalCost: 0 };
    }

    let totalCost = 0;
    
    rosterUnits.forEach((rosterUnit: any) => {
      const unit = availableUnits.find((u: any) => u.id === rosterUnit.unitId);
      if (unit) {
        const weapon = weapons.find((w: any) => 
          w.id === (rosterUnit.selectedWeaponId || unit.defaultWeaponId)
        );
        
        const unitCost = calculateUnitTotalCost(
          {
            quality: unit.quality,
            defense: unit.defense,
            toughness: unit.toughness,
            flags: unit.flags || {}
          },
          weapon ? {
            range: weapon.range,
            attacks: parseFloat(weapon.attacks),
            ap: weapon.ap,
            tags: weapon.tags || []
          } : undefined,
          [], // abilities - TODO: implement
          rosterUnit.count
        );
        
        totalCost += unitCost;
      }
    });

    // For now, breakdown is simplified - in a full implementation, 
    // we'd separate unit base cost, weapon cost, and ability cost
    return {
      unitsCost: Math.round(totalCost * 0.6),
      weaponsCost: Math.round(totalCost * 0.3),
      abilitiesCost: Math.round(totalCost * 0.1),
      totalCost
    };
  };

  const costs = calculateTotalCosts();

  if (rosterLoading || !roster) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 py-6">
          <Skeleton className="h-8 w-64 mb-6" />
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-3">
              <Skeleton className="h-96 w-full" />
            </div>
            <div>
              <Skeleton className="h-64 w-full" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 py-6">
        <Card className="mb-6">
          <CardHeader>
            <div className="flex justify-between items-center">
              <div className="flex items-center space-x-4">
                <Button variant="ghost" size="sm" asChild>
                  <Link href="/rosters" data-testid="button-back">
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back to Rosters
                  </Link>
                </Button>
                <h1 className="text-2xl font-bold" data-testid="text-roster-name">{roster.name}</h1>
              </div>
              <div className="flex items-center space-x-4">
                <div className="flex items-center space-x-2">
                  <Label htmlFor="points-limit">Points Limit:</Label>
                  <Input
                    id="points-limit"
                    type="number"
                    min="500"
                    step="250"
                    value={pointsLimit}
                    onChange={(e) => setPointsLimit(parseInt(e.target.value) || 2000)}
                    onBlur={handleUpdatePointsLimit}
                    className="w-24 text-center"
                    data-testid="input-points-limit"
                  />
                </div>
                <Button variant="outline" asChild>
                  <Link href={`/rosters/${rosterId}/print`} data-testid="button-print">
                    <Printer className="h-4 w-4 mr-2" />
                    Print
                  </Link>
                </Button>
              </div>
            </div>
          </CardHeader>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Available Units */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>Available Units</CardTitle>
                <CardDescription>Units from your selected army</CardDescription>
              </CardHeader>
              <CardContent>
                {unitsLoading ? (
                  <div className="space-y-3">
                    {[1, 2, 3].map(i => (
                      <Skeleton key={i} className="h-24 w-full" />
                    ))}
                  </div>
                ) : availableUnits && availableUnits.length > 0 ? (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {availableUnits.map((unit: any) => {
                      const weapon = weapons?.find((w: any) => w.id === unit.defaultWeaponId);
                      return (
                        <UnitCard
                          key={unit.id}
                          unit={unit}
                          weapon={weapon}
                          onAdd={handleAddUnit}
                          showAddButton={true}
                        />
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center py-6">
                    <p className="text-muted-foreground">No units available in this army</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Current Roster */}
          <div>
            <Card>
              <CardHeader>
                <CardTitle>Current Roster</CardTitle>
                <CardDescription>Your selected units</CardDescription>
              </CardHeader>
              <CardContent>
                {rosterUnitsLoading ? (
                  <div className="space-y-3">
                    {[1, 2].map(i => (
                      <Skeleton key={i} className="h-20 w-full" />
                    ))}
                  </div>
                ) : rosterUnits && rosterUnits.length > 0 ? (
                  <div className="space-y-3 max-h-96 overflow-y-auto">
                    {rosterUnits.map((rosterUnit: any) => {
                      const unit = availableUnits?.find((u: any) => u.id === rosterUnit.unitId);
                      const selectedWeapon = weapons?.find((w: any) => 
                        w.id === (rosterUnit.selectedWeaponId || unit?.defaultWeaponId)
                      );
                      
                      if (!unit) return null;

                      return (
                        <Card key={rosterUnit.id} className="p-3" data-testid={`roster-unit-${rosterUnit.id}`}>
                          <div className="flex justify-between items-start mb-2">
                            <h4 className="font-medium text-sm">{unit.name}</h4>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleRemoveUnit(rosterUnit.id)}
                              data-testid={`button-remove-unit-${rosterUnit.id}`}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                          
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center space-x-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateCount(rosterUnit.id, rosterUnit.count - 1)}
                                disabled={rosterUnit.count <= 1}
                                data-testid={`button-decrease-${rosterUnit.id}`}
                              >
                                <Minus className="h-3 w-3" />
                              </Button>
                              <span className="w-8 text-center text-sm font-medium">
                                {rosterUnit.count}
                              </span>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleUpdateCount(rosterUnit.id, rosterUnit.count + 1)}
                                data-testid={`button-increase-${rosterUnit.id}`}
                              >
                                <Plus className="h-3 w-3" />
                              </Button>
                            </div>
                            <div className="text-right">
                              <span className="text-sm font-medium">
                                {calculateUnitTotalCost(
                                  {
                                    quality: unit.quality,
                                    defense: unit.defense,
                                    toughness: unit.toughness,
                                    flags: unit.flags || {}
                                  },
                                  selectedWeapon ? {
                                    range: selectedWeapon.range,
                                    attacks: parseFloat(selectedWeapon.attacks),
                                    ap: selectedWeapon.ap,
                                    tags: selectedWeapon.tags || []
                                  } : undefined,
                                  [],
                                  rosterUnit.count
                                )} pts
                              </span>
                            </div>
                          </div>

                          <Select
                            value={rosterUnit.selectedWeaponId || unit.defaultWeaponId || ""}
                            onValueChange={(value) => handleUpdateWeapon(rosterUnit.id, value)}
                          >
                            <SelectTrigger className="text-xs">
                              <SelectValue placeholder="Select weapon" />
                            </SelectTrigger>
                            <SelectContent>
                              {weapons?.map((weapon: any) => (
                                <SelectItem key={weapon.id} value={weapon.id}>
                                  {weapon.name} ({weapon.range}", A{weapon.attacks}, AP{weapon.ap})
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </Card>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center py-6">
                    <p className="text-muted-foreground">No units in roster</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Cost Calculator */}
          <div>
            <CostCalculator
              unitsCost={costs.unitsCost}
              weaponsCost={costs.weaponsCost}
              abilitiesCost={costs.abilitiesCost}
              totalCost={costs.totalCost}
              pointsLimit={pointsLimit}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
