import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import { Navbar } from "@/components/navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, Users, Sword, FileText, Target } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  const { data: armies, isLoading: armiesLoading } = useQuery({
    queryKey: ["/api/armies"]
  });

  const { data: rosters, isLoading: rostersLoading } = useQuery({
    queryKey: ["/api/rosters"]
  });

  const { data: weapons, isLoading: weaponsLoading } = useQuery({
    queryKey: ["/api/weapons"]
  });

  const stats = {
    armies: armies?.length || 0,
    rosters: rosters?.length || 0,
    weapons: weapons?.length || 0,
    games: 3 // Placeholder for active games
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold" data-testid="text-page-title">Army Builder Dashboard</h1>
          <div className="flex space-x-3">
            <Button asChild data-testid="button-new-roster">
              <Link href="/rosters">
                <Plus className="h-4 w-4 mr-2" />
                New Roster
              </Link>
            </Button>
            <Button variant="secondary" asChild data-testid="button-new-army">
              <Link href="/armies">
                <Plus className="h-4 w-4 mr-2" />
                New Army
              </Link>
            </Button>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-muted-foreground text-sm">Total Rosters</p>
                  <p className="text-2xl font-bold" data-testid="text-rosters-count">
                    {rostersLoading ? <Skeleton className="h-6 w-8" /> : stats.rosters}
                  </p>
                </div>
                <FileText className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-muted-foreground text-sm">My Armies</p>
                  <p className="text-2xl font-bold" data-testid="text-armies-count">
                    {armiesLoading ? <Skeleton className="h-6 w-8" /> : stats.armies}
                  </p>
                </div>
                <Users className="h-8 w-8 text-secondary" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-muted-foreground text-sm">Weapons</p>
                  <p className="text-2xl font-bold" data-testid="text-weapons-count">
                    {weaponsLoading ? <Skeleton className="h-6 w-8" /> : stats.weapons}
                  </p>
                </div>
                <Sword className="h-8 w-8 text-accent-foreground" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-muted-foreground text-sm">Active Games</p>
                  <p className="text-2xl font-bold" data-testid="text-games-count">{stats.games}</p>
                </div>
                <Target className="h-8 w-8 text-primary" />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Recent Content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Recent Rosters */}
          <Card>
            <CardHeader>
              <CardTitle>Recent Rosters</CardTitle>
              <CardDescription>Your latest army lists</CardDescription>
            </CardHeader>
            <CardContent>
              {rostersLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="flex items-center justify-between py-3">
                      <div className="flex items-center space-x-3">
                        <Skeleton className="w-10 h-10 rounded-lg" />
                        <div>
                          <Skeleton className="h-4 w-32 mb-1" />
                          <Skeleton className="h-3 w-24" />
                        </div>
                      </div>
                      <div className="text-right">
                        <Skeleton className="h-4 w-16 mb-1" />
                        <Skeleton className="h-3 w-20" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : rosters && rosters.length > 0 ? (
                <div className="space-y-3">
                  {rosters.slice(0, 3).map((roster: any) => (
                    <div 
                      key={roster.id} 
                      className="flex items-center justify-between py-3 border-b border-border last:border-b-0"
                      data-testid={`roster-item-${roster.id}`}
                    >
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
                          <FileText className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <p className="font-medium" data-testid={`text-roster-name-${roster.id}`}>
                            {roster.name}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {roster.pointsLimit ? `${roster.pointsLimit} pts` : "No limit"}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <Button variant="ghost" size="sm" asChild>
                          <Link href={`/rosters/${roster.id}/build`}>Edit</Link>
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-6">
                  <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground mb-3">No rosters yet</p>
                  <Button asChild size="sm">
                    <Link href="/rosters">Create Your First Roster</Link>
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* My Armies */}
          <Card>
            <CardHeader>
              <CardTitle>My Armies</CardTitle>
              <CardDescription>Your army collections</CardDescription>
            </CardHeader>
            <CardContent>
              {armiesLoading ? (
                <div className="space-y-4">
                  {[1, 2].map(i => (
                    <div key={i} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                      <div className="flex items-center space-x-3">
                        <Skeleton className="w-10 h-10 rounded-lg" />
                        <div>
                          <Skeleton className="h-4 w-24 mb-1" />
                          <Skeleton className="h-3 w-32" />
                        </div>
                      </div>
                      <Skeleton className="w-8 h-8" />
                    </div>
                  ))}
                </div>
              ) : armies && armies.length > 0 ? (
                <div className="space-y-4">
                  {armies.slice(0, 2).map((army: any) => (
                    <div 
                      key={army.id} 
                      className="flex items-center justify-between p-3 bg-muted rounded-lg"
                      data-testid={`army-item-${army.id}`}
                    >
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
                          <Users className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <p className="font-medium" data-testid={`text-army-name-${army.id}`}>
                            {army.name}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            Army collection
                          </p>
                        </div>
                      </div>
                      <Button variant="ghost" size="sm" asChild>
                        <Link href={`/armies/${army.id}`}>Edit</Link>
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-6">
                  <Users className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
                  <p className="text-muted-foreground mb-3">No armies yet</p>
                  <Button asChild size="sm">
                    <Link href="/armies">Create Your First Army</Link>
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Quick Actions */}
        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="text-center">
            <CardContent className="p-6">
              <Sword className="h-12 w-12 text-primary mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Weapon Database</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Manage your collection of weapons with stats and special abilities
              </p>
              <Button asChild variant="outline" className="w-full">
                <Link href="/armory">Browse Armory</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="text-center">
            <CardContent className="p-6">
              <Users className="h-12 w-12 text-secondary mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Army Management</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Create and organize your armies with units and special rules
              </p>
              <Button asChild variant="outline" className="w-full">
                <Link href="/armies">Manage Armies</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="text-center">
            <CardContent className="p-6">
              <FileText className="h-12 w-12 text-accent-foreground mx-auto mb-3" />
              <h3 className="font-semibold mb-2">List Building</h3>
              <p className="text-sm text-muted-foreground mb-4">
                Build competitive rosters with real-time cost calculation
              </p>
              <Button asChild variant="outline" className="w-full">
                <Link href="/rosters">Build Lists</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
