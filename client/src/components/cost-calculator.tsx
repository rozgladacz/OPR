import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface CostCalculatorProps {
  unitsCost: number;
  weaponsCost: number;
  abilitiesCost: number;
  totalCost: number;
  pointsLimit?: number;
}

export function CostCalculator({ 
  unitsCost, 
  weaponsCost, 
  abilitiesCost, 
  totalCost, 
  pointsLimit = 2000 
}: CostCalculatorProps) {
  const remaining = pointsLimit - totalCost;
  const percentage = Math.min((totalCost / pointsLimit) * 100, 100);

  return (
    <Card className="sticky top-6" data-testid="cost-calculator">
      <CardHeader>
        <CardTitle className="text-lg">Point Summary</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span>Units Cost:</span>
            <span data-testid="text-units-cost">{unitsCost}</span>
          </div>
          <div className="flex justify-between">
            <span>Weapons:</span>
            <span data-testid="text-weapons-cost">{weaponsCost}</span>
          </div>
          <div className="flex justify-between">
            <span>Abilities:</span>
            <span data-testid="text-abilities-cost">{abilitiesCost}</span>
          </div>
          <hr className="border-border" />
          <div className="flex justify-between font-semibold text-lg">
            <span>Total:</span>
            <span className="text-primary" data-testid="text-total-cost">
              {totalCost} pts
            </span>
          </div>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>Remaining:</span>
            <span data-testid="text-remaining-cost">{remaining} pts</span>
          </div>
        </div>
        
        <div>
          <Progress value={percentage} className="w-full" />
          <p className="text-xs text-muted-foreground mt-1 text-center" data-testid="text-percentage">
            {percentage.toFixed(1)}% of points limit used
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
