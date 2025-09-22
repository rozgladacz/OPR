import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link } from "wouter";
import { Navbar } from "@/components/navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Plus, FileText, Edit, Trash2, Printer, Calendar } from "lucide-react";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function RostersPage() {
  const { toast } = useToast();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [rosterForm, setRosterForm] = useState({
    name: "",
    armyId: "",
    pointsLimit: "2000"
  });

  const { data: rosters, isLoading: rostersLoading } = useQuery({
    queryKey: ["/api/rosters"]
  });

  const { data: armies } = useQuery({
    queryKey: ["/api/armies"]
  });

  const createRosterMutation = useMutation({
    mutationFn: async (rosterData: any) => {
      const res = await apiRequest("POST", "/api/rosters", {
        ...rosterData,
        pointsLimit: parseInt(rosterData.pointsLimit) || null
      });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/rosters"] });
      setIsCreateOpen(false);
      setRosterForm({
        name: "",
        armyId: "",
        pointsLimit: "2000"
      });
      toast({
        title: "Roster created",
        description: "Your new roster has been created successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to create roster",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteRosterMutation = useMutation({
    mutationFn: async (rosterId: string) => {
      await apiRequest("DELETE", `/api/rosters/${rosterId}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/rosters"] });
      toast({
        title: "Roster deleted",
        description: "The roster has been deleted successfully.",
      });
    },
    onError: (error) => {
      toast({
        title: "Failed to delete roster",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleCreateRoster = (e: React.FormEvent) => {
    e.preventDefault();
    if (rosterForm.name.trim() && rosterForm.armyId) {
      createRosterMutation.mutate(rosterForm);
    }
  };

  const handleDeleteRoster = (rosterId: string, rosterName: string) => {
    if (confirm(`Are you sure you want to delete "${rosterName}"? This action cannot be undone.`)) {
      deleteRosterMutation.mutate(rosterId);
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold" data-testid="text-page-title">Army Rosters</h1>
          <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
            <DialogTrigger asChild>
              <Button data-testid="button-create-roster">
                <Plus className="h-4 w-4 mr-2" />
                Create Roster
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New Roster</DialogTitle>
                <DialogDescription>
                  Create a new army roster for tournament play or casual games.
                </DialogDescription>
              </DialogHeader>
              <form onSubmit={handleCreateRoster} className="space-y-4">
                <div>
                  <Label htmlFor="roster-name">Roster Name</Label>
                  <Input
                    id="roster-name"
                    value={rosterForm.name}
                    onChange={(e) => setRosterForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Enter roster name"
                    required
                    data-testid="input-roster-name"
                  />
                </div>
                
                <div>
                  <Label htmlFor="roster-army">Army</Label>
                  <Select
                    value={rosterForm.armyId}
                    onValueChange={(value) => setRosterForm(prev => ({ ...prev, armyId: value }))}
                  >
                    <SelectTrigger data-testid="select-roster-army">
                      <SelectValue placeholder="Select an army" />
                    </SelectTrigger>
                    <SelectContent>
                      {armies?.map((army: any) => (
                        <SelectItem key={army.id} value={army.id}>
                          {army.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="roster-points">Points Limit</Label>
                  <Input
                    id="roster-points"
                    type="number"
                    min="500"
                    step="250"
                    value={rosterForm.pointsLimit}
                    onChange={(e) => setRosterForm(prev => ({ ...prev, pointsLimit: e.target.value }))}
                    placeholder="2000"
                    data-testid="input-roster-points"
                  />
                  <p className="text-xs text-muted-foreground mt-1">
                    Leave empty for unlimited points
                  </p>
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
                    disabled={createRosterMutation.isPending || !rosterForm.armyId}
                    data-testid="button-submit-roster"
                  >
                    {createRosterMutation.isPending ? "Creating..." : "Create Roster"}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {rostersLoading ? (
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
                    <Skeleton className="h-10 w-full" />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : rosters && rosters.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {rosters.map((roster: any) => (
              <Card key={roster.id} data-testid={`card-roster-${roster.id}`}>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <FileText className="h-5 w-5" />
                    <span data-testid={`text-roster-name-${roster.id}`}>{roster.name}</span>
                  </CardTitle>
                  <CardDescription className="flex items-center space-x-4">
                    <span>
                      {roster.pointsLimit ? `${roster.pointsLimit} pts limit` : "Unlimited points"}
                    </span>
                    {roster.updatedAt && (
                      <span className="flex items-center space-x-1">
                        <Calendar className="h-3 w-3" />
                        <span>{formatDate(roster.updatedAt)}</span>
                      </span>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex space-x-2">
                    <Button asChild className="flex-1">
                      <Link href={`/rosters/${roster.id}/build`} data-testid={`button-edit-roster-${roster.id}`}>
                        <Edit className="h-4 w-4 mr-2" />
                        Edit
                      </Link>
                    </Button>
                    <Button variant="outline" size="icon" asChild>
                      <Link href={`/rosters/${roster.id}/print`} data-testid={`button-print-roster-${roster.id}`}>
                        <Printer className="h-4 w-4" />
                      </Link>
                    </Button>
                    <Button
                      variant="destructive"
                      size="icon"
                      onClick={() => handleDeleteRoster(roster.id, roster.name)}
                      disabled={deleteRosterMutation.isPending}
                      data-testid={`button-delete-roster-${roster.id}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <FileText className="h-24 w-24 text-muted-foreground mx-auto mb-6" />
            <h2 className="text-2xl font-bold mb-2">No Rosters Yet</h2>
            <p className="text-muted-foreground mb-6">
              Create your first roster to start building competitive army lists.
            </p>
            <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
              <DialogTrigger asChild>
                <Button size="lg">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Your First Roster
                </Button>
              </DialogTrigger>
            </Dialog>
          </div>
        )}
      </div>
    </div>
  );
}
