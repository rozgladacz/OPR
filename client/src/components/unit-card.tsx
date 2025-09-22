import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";

interface UnitCardProps {
  unit: {
    id: string;
    name: string;
    quality: number;
    defense: number;
    toughness: number;
    cachedCost?: string;
  };
  weapon?: {
    name: string;
    range: string;
    attacks: number;
    ap: number;
  };
  onAdd?: (unitId: string) => void;
  showAddButton?: boolean;
}

export function UnitCard({ unit, weapon, onAdd, showAddButton = false }: UnitCardProps) {
  const formatStat = (value: number) => `${value}+`;

  return (
    <Card 
      className="hover:shadow-sm transition-shadow cursor-pointer" 
      data-testid={`card-unit-${unit.id}`}
    >
      <CardContent className="p-4">
        <div className="flex justify-between items-start">
          <div className="flex-1">
            <h4 className="font-medium mb-2" data-testid={`text-unit-name-${unit.id}`}>
              {unit.name}
            </h4>
            <div className="flex items-center space-x-4 mb-2">
              <div className="flex items-center space-x-1">
                <span className="text-xs text-muted-foreground">Q:</span>
                <Badge variant="outline" className="bg-primary/10 text-primary">
                  {formatStat(unit.quality)}
                </Badge>
              </div>
              <div className="flex items-center space-x-1">
                <span className="text-xs text-muted-foreground">D:</span>
                <Badge variant="outline" className="bg-secondary/10 text-secondary">
                  {formatStat(unit.defense)}
                </Badge>
              </div>
              <div className="flex items-center space-x-1">
                <span className="text-xs text-muted-foreground">T:</span>
                <Badge variant="outline" className="bg-accent/30 text-accent-foreground">
                  {unit.toughness}
                </Badge>
              </div>
            </div>
            {weapon && (
              <p className="text-xs text-muted-foreground" data-testid={`text-weapon-${unit.id}`}>
                {weapon.name} ({weapon.range}", A{weapon.attacks}, AP{weapon.ap})
              </p>
            )}
          </div>
          <div className="text-right">
            <span 
              className="text-sm font-medium" 
              data-testid={`text-cost-${unit.id}`}
            >
              {unit.cachedCost || "0"} pts
            </span>
            {showAddButton && onAdd && (
              <Button
                size="sm"
                className="block w-full mt-1"
                onClick={() => onAdd(unit.id)}
                data-testid={`button-add-unit-${unit.id}`}
              >
                <Plus className="h-3 w-3 mr-1" />
                Add
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
