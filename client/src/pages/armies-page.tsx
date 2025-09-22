import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "wouter";
import { Navbar } from "@/components/navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Plus, Users, Edit, Trash2 } from "lucide-react";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function ArmiesPage() {
  const { toast } = useToast();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newArmyName, setNewArmyName] = useState("");

  const { data: armies, isLoading } = useQuery({
    queryKey: ["/api/armies"]
  });

  const createArmyMutation = useMutation({
    mutationFn: async (name: string) => {
      const res = await apiRequest("POST", "/api/armies", { 
        name,
        rulesetId: "default" 
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/armies"] });
      setIsCreateOpen(false);
      setNewArmyName("");
      toast({
        title: "Army created",
        description: "Your new army has been created successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to create army",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteArmyMutation = useMutation({
    mutationFn: async (armyId: string) => {
      await apiRequest("DELETE", `/api/armies/${armyId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/armies"] });
      toast({
        title: "Army deleted",
        description: "The army has been deleted successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to delete army",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleCreateArmy = (e: React.FormEvent) => {
    e.preventDefault();
    if (newArmyName.trim()) {
      createArmyMutation.mutate(newArmyName.trim());
    }
  };

  const handleDeleteArmy = (armyId: string, armyName: string) => {
    if (confirm(`Are you sure you want to delete "${armyName}"? This action cannot be undone.`)) {
      deleteArmyMutation.mutate(armyId);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold" data-testid="text-page-title">Army Management</h1>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button data-testid="button-create-army">
                <Plus className="h-4 w-4 mr-2" />
                Create Army
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New Army</DialogTitle>
                <DialogDescription>
                  Create a new army to organize your units and weapons.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateArmy} className="space-y-4">
                <div>
                  <Label htmlFor="army-name">Army Name</Label>
                  <Input
                    id="army-name"
                    value={newArmyName}
                    onChange={(e) => setNewArmyName(e.target.value)}
                    placeholder="Enter army name"
                    required
                    data-testid="input-army-name"
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
                    disabled={createArmyMutation.isPending}
                    data-testid="button-submit-army"
                  >
                    {createArmyMutation.isPending ? "Creating..." : "Create Army"}
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
                  <Skeleton className="h-10 w-full" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : armies && armies.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {armies.map((army: any) => (
              <Card key={army.id} data-testid={`card-army-${army.id}`}>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Users className="h-5 w-5" />
                    <span data-testid={`text-army-name-${army.id}`}>{army.name}</span>
                  </CardTitle>
                  <CardDescription>
                    Army collection • {army.ownerId ? "Personal" : "Global"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex space-x-2">
                    <Button asChild className="flex-1">
                      <Link href={`/armies/${army.id}`} data-testid={`button-edit-army-${army.id}`}>
                        <Edit className="h-4 w-4 mr-2" />
                        Edit
                      </Link>
                    </Button>
                    {army.ownerId && (
                      <Button
                        variant="destructive"
                        size="icon"
                        onClick={() => handleDeleteArmy(army.id, army.name)}
                        disabled={deleteArmyMutation.isPending}
                        data-testid={`button-delete-army-${army.id}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <Users className="h-24 w-24 text-muted-foreground mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-2">No Armies Yet</h2>
            <p className="text-muted-foreground mb-6">
              Create your first army to start building units and organizing your collection.
            </p>
            <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
              <DialogTrigger asChild>
                <Button size="lg">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Your First Army
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>
        )}
      </div>
    </div>
  );
}
