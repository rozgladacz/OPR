import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useRoute } from "wouter";
import { Navbar } from "@/components/navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Plus, Edit, Trash2, ArrowLeft } from "lucide-react";
import { Link } from "wouter";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function ArmyDetailPage() {
  const [, params] = useRoute("/armies/:id");
  const armyId = params?.id;
  const { toast } = useToast();
  
  const [isCreateUnitOpen, setIsCreateUnitOpen] = useState(false);
  const [unitForm, setUnitForm] = useState({
    name: "",
    quality: 4,
    defense: 4,
    toughness: 1,
    defaultWeaponId: ""
  });

  const { data: army, isLoading: armyLoading } = useQuery({
    queryKey: ["/api/armies", armyId],
    enabled: !!armyId
  });

  const { data: units, isLoading: unitsLoading } = useQuery({
    queryKey: ["/api/armies", armyId, "units"],
    enabled: !!armyId
  });

  const { data: weapons } = useQuery({
    queryKey: ["/api/weapons"]
  });

  const createUnitMutation = useMutation({
    mutationFn: async (unitData: any) => {
      const res = await apiRequest("POST", `/api/armies/${armyId}/units`, unitData);
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/armies", armyId, "units"] });
      setIsCreateUnitOpen(false);
      setUnitForm({
        name: "",
        quality: 4,
        defense: 4,
        toughness: 1,
        defaultWeaponId: ""
      });
      toast({
        title: "Unit created",
        description: "Your new unit has been created successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to create unit",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteUnitMutation = useMutation({
    mutationFn: async (unitId: string) => {
      await apiRequest("DELETE", `/api/units/${unitId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/armies", armyId, "units"] });
      toast({
        title: "Unit deleted",
        description: "The unit has been deleted successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to delete unit",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleCreateUnit = (e: React.FormEvent) => {
    e.preventDefault();
    createUnitMutation.mutate({
      ...unitForm,
      defaultWeaponId: unitForm.defaultWeaponId || null
    });
  };

  const handleDeleteUnit = (unitId: string, unitName: string) => {
    if (confirm(`Are you sure you want to delete "${unitName}"? This action cannot be undone.`)) {
      deleteUnitMutation.mutate(unitId);
    }
  };

  const formatStat = (value: number) => `${value}+`;

  if (armyLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 py-6">
          <Skeleton className="h-8 w-64 mb-6" />
          <div className="grid gap-6">
            {[1, 2, 3].map(i => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!army) {
    return (
      <div className="min-h-screen bg-background">
        <Navbar />
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="text-center py-12">
            <h1 className="text-2xl font-bold mb-4">Army Not Found</h1>
            <Button asChild>
              <Link href="/armies">
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to Armies
              </Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex items-center space-x-4 mb-6">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/armies" data-testid="button-back">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Armies
            </Link>
          </Button>
          <h1 className="text-3xl font-bold" data-testid="text-army-name">{army.name}</h1>
        </div>

        <div className="flex justify-between items-center mb-6">
          <div>
            <p className="text-muted-foreground">
              Manage units and their equipment for this army
            </p>
          </div>
          <Dialog open={isCreateUnitOpen} onOpenChange={setIsCreateUnitOpen}>
            <DialogTrigger asChild>
              <Button data-testid="button-create-unit">
                <Plus className="h-4 w-4 mr-2" />
                Add Unit
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New Unit</DialogTitle>
                <DialogDescription>
                  Add a new unit to your army with stats and equipment.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateUnit} className="space-y-4">
                <div>
                  <Label htmlFor="unit-name">Unit Name</Label>
                  <Input
                    id="unit-name"
                    value={unitForm.name}
                    onChange={(e) => setUnitForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Enter unit name"
                    required
                    data-testid="input-unit-name"
                  />
                </div>
                
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <Label htmlFor="unit-quality">Quality</Label>
                    <Select
                      value={unitForm.quality.toString()}
                      onValueChange={(value) => setUnitForm(prev => ({ ...prev, quality: parseInt(value) }))}
                    >
                      <SelectTrigger data-testid="select-unit-quality">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="2">2+</SelectItem>
                        <SelectItem value="3">3+</SelectItem>
                        <SelectItem value="4">4+</SelectItem>
                        <SelectItem value="5">5+</SelectItem>
                        <SelectItem value="6">6+</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <Label htmlFor="unit-defense">Defense</Label>
                    <Select
                      value={unitForm.defense.toString()}
                      onValueChange={(value) => setUnitForm(prev => ({ ...prev, defense: parseInt(value) }))}
                    >
                      <SelectTrigger data-testid="select-unit-defense">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="2">2+</SelectItem>
                        <SelectItem value="3">3+</SelectItem>
                        <SelectItem value="4">4+</SelectItem>
                        <SelectItem value="5">5+</SelectItem>
                        <SelectItem value="6">6+</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  
                  <div>
                    <Label htmlFor="unit-toughness">Toughness</Label>
                    <Input
                      id="unit-toughness"
                      type="number"
                      min="1"
                      max="20"
                      value={unitForm.toughness}
                      onChange={(e) => setUnitForm(prev => ({ ...prev, toughness: parseInt(e.target.value) || 1 }))}
                      data-testid="input-unit-toughness"
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="unit-weapon">Default Weapon</Label>
                  <Select
                    value={unitForm.defaultWeaponId}
                    onValueChange={(value) => setUnitForm(prev => ({ ...prev, defaultWeaponId: value }))}
                  >
                    <SelectTrigger data-testid="select-unit-weapon">
                      <SelectValue placeholder="Select weapon (optional)" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="">No weapon</SelectItem>
                      {weapons?.map((weapon: any) => (
                        <SelectItem key={weapon.id} value={weapon.id}>
                          {weapon.name} ({weapon.range}", A{weapon.attacks}, AP{weapon.ap})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex justify-end space-x-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setIsCreateUnitOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={createUnitMutation.isPending}
                    data-testid="button-submit-unit"
                  >
                    {createUnitMutation.isPending ? "Creating..." : "Create Unit"}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {unitsLoading ? (
          <div className="grid gap-4">
            {[1, 2, 3].map(i => (
              <Skeleton key={i} className="h-24 w-full" />
            ))}
          </div>
        ) : units && units.length > 0 ? (
          <div className="grid gap-4">
            {units.map((unit: any) => (
              <Card key={unit.id} data-testid={`card-unit-${unit.id}`}>
                <CardContent className="p-6">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold mb-2" data-testid={`text-unit-name-${unit.id}`}>
                        {unit.name}
                      </h3>
                      <div className="flex items-center space-x-6 mb-3">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-muted-foreground">Quality:</span>
                          <Badge variant="outline" className="bg-primary/10 text-primary">
                            {formatStat(unit.quality)}
                          </Badge>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-muted-foreground">Defense:</span>
                          <Badge variant="outline" className="bg-secondary/10 text-secondary">
                            {formatStat(unit.defense)}
                          </Badge>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className="text-sm text-muted-foreground">Toughness:</span>
                          <Badge variant="outline" className="bg-accent/30 text-accent-foreground">
                            {unit.toughness}
                          </Badge>
                        </div>
                      </div>
                      {unit.defaultWeaponId && (
                        <p className="text-sm text-muted-foreground">
                          Default weapon assigned
                        </p>
                      )}
                    </div>
                    <div className="flex space-x-2">
                      <Button variant="outline" size="sm">
                        <Edit className="h-4 w-4 mr-2" />
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        size="sm"
                        onClick={() => handleDeleteUnit(unit.id, unit.name)}
                        disabled={deleteUnitMutation.isPending}
                        data-testid={`button-delete-unit-${unit.id}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <Plus className="h-24 w-24 text-muted-foreground mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-2">No Units Yet</h2>
            <p className="text-muted-foreground mb-6">
              Add units to this army to start building your forces.
            </p>
            <Dialog open={isCreateUnitOpen} onOpenChange={setIsCreateUnitOpen}>
              <DialogTrigger asChild>
                <Button size="lg">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Your First Unit
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>
        )}
      </div>
    </div>
  );
}
