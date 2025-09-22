import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/hooks/use-auth";
import { ProtectedRoute } from "./lib/protected-route";
import HomePage from "@/pages/home-page";
import AuthPage from "@/pages/auth-page";
import ArmiesPage from "@/pages/armies-page";
import ArmyDetailPage from "@/pages/army-detail-page";
import ArmoryPage from "@/pages/armory-page";
import RostersPage from "@/pages/rosters-page";
import RosterBuilderPage from "@/pages/roster-builder-page";
import RosterPrintPage from "@/pages/roster-print-page";
import NotFound from "@/pages/not-found";

function Router() {
  return (
    <Switch>
      <ProtectedRoute path="/" component={HomePage} />
      <ProtectedRoute path="/armies" component={ArmiesPage} />
      <ProtectedRoute path="/armies/:id" component={ArmyDetailPage} />
      <ProtectedRoute path="/armory" component={ArmoryPage} />
      <ProtectedRoute path="/rosters" component={RostersPage} />
      <ProtectedRoute path="/rosters/:id/build" component={RosterBuilderPage} />
      <ProtectedRoute path="/rosters/:id/print" component={RosterPrintPage} />
      <Route path="/auth" component={AuthPage} />
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
