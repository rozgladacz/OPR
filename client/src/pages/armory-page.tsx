import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Navbar } from "@/components/navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Sword, Edit, Trash2 } from "lucide-react";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function ArmoryPage() {
  const { toast } = useToast();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [weaponForm, setWeaponForm] = useState({
    name: "",
    range: "",
    attacks: "1",
    ap: "0",
    tags: "",
    notes: ""
  });

  const { data: weapons, isLoading } = useQuery({
    queryKey: ["/api/weapons"]
  });

  const createWeaponMutation = useMutation({
    mutationFn: async (weaponData: any) => {
      const res = await apiRequest("POST", "/api/weapons", {
        ...weaponData,
        attacks: parseFloat(weaponData.attacks),
        ap: parseInt(weaponData.ap),
        tags: weaponData.tags.split(",").map((tag: string) => tag.trim()).filter(Boolean)
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/weapons"] });
      setIsCreateOpen(false);
      setWeaponForm({
        name: "",
        range: "",
        attacks: "1",
        ap: "0",
        tags: "",
        notes: ""
      });
      toast({
        title: "Weapon created",
        description: "Your new weapon has been created successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to create weapon",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteWeaponMutation = useMutation({
    mutationFn: async (weaponId: string) => {
      await apiRequest("DELETE", `/api/weapons/${weaponId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/weapons"] });
      toast({
        title: "Weapon deleted",
        description: "The weapon has been deleted successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to delete weapon",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleCreateWeapon = (e: React.FormEvent) => {
    e.preventDefault();
    createWeaponMutation.mutate(weaponForm);
  };

  const handleDeleteWeapon = (weaponId: string, weaponName: string) => {
    if (confirm(`Are you sure you want to delete "${weaponName}"? This action cannot be undone.`)) {
      deleteWeaponMutation.mutate(weaponId);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold" data-testid="text-page-title">Weapon Armory</h1>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button data-testid="button-create-weapon">
                <Plus className="h-4 w-4 mr-2" />
                Add Weapon
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Create New Weapon</DialogTitle>
                <DialogDescription>
                  Add a new weapon to your armory with stats and special abilities.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateWeapon} className="space-y-4">
                <div>
                  <Label htmlFor="weapon-name">Weapon Name</Label>
                  <Input
                    id="weapon-name"
                    value={weaponForm.name}
                    onChange={(e) => setWeaponForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Enter weapon name"
                    required
                    data-testid="input-weapon-name"
                  />
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="weapon-range">Range</Label>
                    <Input
                      id="weapon-range"
                      value={weaponForm.range}
                      onChange={(e) => setWeaponForm(prev => ({ ...prev, range: e.target.value }))}
                      placeholder="24 or melee"
                      required
                      data-testid="input-weapon-range"
                    />
                  </div>
                  
                  <div>
                    <Label htmlFor="weapon-attacks">Attacks</Label>
                    <Input
                      id="weapon-attacks"
                      type="number"
                      step="0.1"
                      min="0.1"
                      value={weaponForm.attacks}
                      onChange={(e) => setWeaponForm(prev => ({ ...prev, attacks: e.target.value }))}
                      required
                      data-testid="input-weapon-attacks"
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="weapon-ap">Armor Piercing (AP)</Label>
                  <Input
                    id="weapon-ap"
                    type="number"
                    min="-1"
                    max="10"
                    value={weaponForm.ap}
                    onChange={(e) => setWeaponForm(prev => ({ ...prev, ap: e.target.value }))}
                    data-testid="input-weapon-ap"
                  />
                </div>

                <div>
                  <Label htmlFor="weapon-tags">Special Abilities</Label>
                  <Input
                    id="weapon-tags"
                    value={weaponForm.tags}
                    onChange={(e) => setWeaponForm(prev => ({ ...prev, tags: e.target.value }))}
                    placeholder="Deadly(3), Blast(3), Reliable (comma separated)"
                    data-testid="input-weapon-tags"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Separate multiple abilities with commas
                  </p>
                </div>

                <div>
                  <Label htmlFor="weapon-notes">Notes</Label>
                  <Textarea
                    id="weapon-notes"
                    value={weaponForm.notes}
                    onChange={(e) => setWeaponForm(prev => ({ ...prev, notes: e.target.value }))}
                    placeholder="Additional notes about this weapon"
                    rows={2}
                    data-testid="input-weapon-notes"
                  />
                </div>

                <div className="flex justify-end space-x-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setIsCreateOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={createWeaponMutation.isPending}
                    data-testid="button-submit-weapon"
                  >
                    {createWeaponMutation.isPending ? "Creating..." : "Create Weapon"}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-6 w-3/4" />
                  <Skeleton className="h-4 w-1/2" />
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-8 w-full" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : weapons && weapons.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {weapons.map((weapon: any) => (
              <Card key={weapon.id} data-testid={`card-weapon-${weapon.id}`}>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Sword className="h-5 w-5" />
                    <span data-testid={`text-weapon-name-${weapon.id}`}>{weapon.name}</span>
                  </CardTitle>
                  <CardDescription>
                    Range: {weapon.range}" • A{weapon.attacks} • AP{weapon.ap}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {weapon.tags && weapon.tags.length > 0 && (
                      <div>
                        <p className="text-sm font-medium mb-1">Special Abilities:</p>
                        <div className="flex flex-wrap gap-1">
                          {weapon.tags.map((tag: string, index: number) => (
                            <Badge key={index} variant="secondary" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                    
                    {weapon.notes && (
                      <div>
                        <p className="text-sm font-medium mb-1">Notes:</p>
                        <p className="text-xs text-muted-foreground">{weapon.notes}</p>
                      </div>
                    )}

                    <div className="flex space-x-2 pt-2">
                      <Button variant="outline" size="sm" className="flex-1">
                        <Edit className="h-3 w-3 mr-1" />
                        Edit
                      </Button>
                      {weapon.ownerId && (
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleDeleteWeapon(weapon.id, weapon.name)}
                          disabled={deleteWeaponMutation.isPending}
                          data-testid={`button-delete-weapon-${weapon.id}`}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <Sword className="h-24 w-24 text-muted-foreground mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-2">No Weapons Yet</h2>
            <p className="text-muted-foreground mb-6">
              Create your first weapon to start building your armory collection.
            </p>
            <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
              <DialogTrigger asChild>
                <Button size="lg">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Your First Weapon
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>
        )}
      </div>
    </div>
  );
}
