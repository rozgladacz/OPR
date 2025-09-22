import { useQuery } from "@tanstack/react-query";
import { useRoute, Link } from "wouter";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, Printer } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { calculateUnitTotalCost } from "@/lib/cost-calculator";

export default function RosterPrintPage() {
  const [, params] = useRoute("/rosters/:id/print");
  const rosterId = params?.id;

  const { data: roster, isLoading: rosterLoading } = useQuery({
    queryKey: ["/api/rosters", rosterId],
    enabled: !!rosterId
  });

  const { data: rosterUnits, isLoading: rosterUnitsLoading } = useQuery({
    queryKey: ["/api/rosters", rosterId, "units"],
    enabled: !!rosterId
  });

  const { data: availableUnits } = useQuery({
    queryKey: ["/api/armies", roster?.armyId, "units"],
    enabled: !!roster?.armyId
  });

  const { data: weapons } = useQuery({
    queryKey: ["/api/weapons"]
  });

  const { data: army } = useQuery({
    queryKey: ["/api/armies", roster?.armyId],
    enabled: !!roster?.armyId
  });

  const formatStat = (value: number) => `${value}+`;

  const calculateTotalCost = () => {
    if (!rosterUnits || !availableUnits || !weapons) return 0;

    return rosterUnits.reduce((total: number, rosterUnit: any) => {
      const unit = availableUnits.find((u: any) => u.id === rosterUnit.unitId);
      if (!unit) return total;

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
        [],
        rosterUnit.count
      );
      
      return total + unitCost;
    }, 0);
  };

  const totalCost = calculateTotalCost();

  const handlePrint = () => {
    window.print();
  };

  if (rosterLoading || !roster) {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-4xl mx-auto px-4 py-6">
          <Skeleton className="h-8 w-64 mb-6" />
          <div className="space-y-6">
            {[1, 2, 3].map(i => (
              <Skeleton key={i} className="h-48 w-full" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {/* No-print header */}
      <div className="no-print bg-card border-b px-4 py-3">
        <div className="max-w-4xl mx-auto flex justify-between items-center">
          <Button variant="ghost" size="sm" asChild>
            <Link href={`/rosters/${rosterId}/build`} data-testid="button-back">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Builder
            </Link>
          </Button>
          <Button onClick={handlePrint} data-testid="button-print">
            <Printer className="h-4 w-4 mr-2" />
            Print Roster
          </Button>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* Roster Header */}
        <div className="text-center mb-8 print-section">
          <h1 className="text-3xl font-bold mb-2" data-testid="text-roster-name">
            {roster.name}
          </h1>
          <div className="flex justify-center items-center space-x-6 text-muted-foreground">
            <span>Army: <strong>{army?.name || "Unknown Army"}</strong></span>
            <span>
              Points: <strong className="text-primary">{totalCost}</strong>
              {roster.pointsLimit && <span> / <strong>{roster.pointsLimit}</strong></span>}
            </span>
            <span>Units: <strong>{rosterUnits?.length || 0}</strong></span>
          </div>
        </div>

        {rosterUnitsLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map(i => (
              <Skeleton key={i} className="h-48 w-full" />
            ))}
          </div>
        ) : rosterUnits && rosterUnits.length > 0 ? (
          <>
            {/* Unit Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
              {rosterUnits.map((rosterUnit: any) => {
                const unit = availableUnits?.find((u: any) => u.id === rosterUnit.unitId);
                const weapon = weapons?.find((w: any) => 
                  w.id === (rosterUnit.selectedWeaponId || unit?.defaultWeaponId)
                );
                
                if (!unit) return null;

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
                  [],
                  rosterUnit.count
                );

                return (
                  <Card 
                    key={rosterUnit.id} 
                    className="unit-card border-2 print-section"
                    data-testid={`print-unit-${rosterUnit.id}`}
                  >
                    <CardContent className="p-4">
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <h3 className="text-lg font-bold">{unit.name}</h3>
                          <p className="text-sm text-muted-foreground">
                            Count: <span className="font-medium">{rosterUnit.count}</span>
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-lg font-bold text-primary">{unitCost} pts</p>
                          <p className="text-xs text-muted-foreground">
                            {Math.round(unitCost / rosterUnit.count)} pts each
                          </p>
                        </div>
                      </div>
                      
                      {/* Stats Row */}
                      <div className="flex items-center space-x-4 mb-3">
                        <div className="text-center">
                          <p className="text-xs text-muted-foreground">Quality</p>
                          <Badge className="bg-primary text-primary-foreground">
                            {formatStat(unit.quality)}
                          </Badge>
                        </div>
                        <div className="text-center">
                          <p className="text-xs text-muted-foreground">Defense</p>
                          <Badge className="bg-secondary text-secondary-foreground">
                            {formatStat(unit.defense)}
                          </Badge>
                        </div>
                        <div className="text-center">
                          <p className="text-xs text-muted-foreground">Toughness</p>
                          <Badge className="bg-accent text-accent-foreground">
                            {unit.toughness}
                          </Badge>
                        </div>
                      </div>

                      {/* Weapons */}
                      {weapon && (
                        <div className="mb-3">
                          <h4 className="text-sm font-semibold mb-1">Weapons</h4>
                          <div className="text-xs">
                            <div className="flex justify-between">
                              <span>{weapon.name}</span>
                              <span className="text-muted-foreground">
                                {weapon.range}", A{weapon.attacks}, AP{weapon.ap}
                                {weapon.tags && weapon.tags.length > 0 && (
                                  <span>, {weapon.tags.join(", ")}</span>
                                )}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Special Rules */}
                      <div>
                        <h4 className="text-sm font-semibold mb-1">Special Rules</h4>
                        <div className="text-xs text-muted-foreground">
                          {unit.flags && Object.keys(unit.flags).length > 0 ? (
                            Object.keys(unit.flags).join(", ")
                          ) : (
                            "Standard unit"
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>

            {/* Summary Table */}
            <div className="print-section">
              <h3 className="text-lg font-bold mb-4">Army Summary</h3>
              <div className="overflow-hidden border rounded-lg">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="bg-muted">
                      <th className="border p-3 text-left">Unit</th>
                      <th className="border p-3 text-center">Count</th>
                      <th className="border p-3 text-center">Cost Each</th>
                      <th className="border p-3 text-center">Total Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rosterUnits.map((rosterUnit: any) => {
                      const unit = availableUnits?.find((u: any) => u.id === rosterUnit.unitId);
                      if (!unit) return null;

                      const weapon = weapons?.find((w: any) => 
                        w.id === (rosterUnit.selectedWeaponId || unit.defaultWeaponId)
                      );
                      
                      const totalUnitCost = calculateUnitTotalCost(
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
                        [],
                        rosterUnit.count
                      );

                      const costEach = Math.round(totalUnitCost / rosterUnit.count);

                      return (
                        <tr key={rosterUnit.id}>
                          <td className="border p-3">{unit.name}</td>
                          <td className="border p-3 text-center">{rosterUnit.count}</td>
                          <td className="border p-3 text-center">{costEach}</td>
                          <td className="border p-3 text-center font-medium">{totalUnitCost}</td>
                        </tr>
                      );
                    })}
                    <tr className="bg-muted font-bold">
                      <td className="border p-3" colSpan={3}>Total Army Cost</td>
                      <td className="border p-3 text-center text-primary">{totalCost} pts</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Rules Reference */}
            <div className="mt-8 text-xs text-muted-foreground print-section">
              <h4 className="font-semibold mb-2">Quick Rules Reference</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p><strong>Quality Test:</strong> Roll 1d6, succeed on result ≥ Quality value</p>
                  <p><strong>Defense Test:</strong> Roll 1d6, succeed on result ≥ Defense value</p>
                  <p><strong>AP (Armor Piercing):</strong> Target gets -AP to defense rolls</p>
                </div>
                <div>
                  <p><strong>Deadly(X):</strong> Instead of 1 wound, deal X wounds simultaneously</p>
                  <p><strong>Blast(X):</strong> Number of hits multiplied by X (max models in unit)</p>
                  <p><strong>Reliable:</strong> Attack with Quality 2+ instead of unit's Quality</p>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="text-center py-12">
            <p className="text-muted-foreground">No units in this roster</p>
          </div>
        )}
      </div>
    </div>
  );
}
