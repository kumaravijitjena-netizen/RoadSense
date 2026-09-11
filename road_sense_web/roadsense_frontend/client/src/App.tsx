import { useEffect, useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";
import NotFound from "./pages/NotFound";
import SignIn from "./pages/SignIn";
import SignUp from "./pages/SignUp";

function LoadingScreen() {
  return <div className="loading-screen"><div className="loading-orbit" /><div className="loading-mark">◎</div><div className="loading-word">RoadSense<span>.</span></div><div className="loading-skeleton"><i /><i /><i /></div><div className="loading-caption">Synchronizing city signal</div></div>;
}

function HomeGate() {
  const [ready, setReady] = useState(false);
  useEffect(() => { const timer = window.setTimeout(() => setReady(true), 850); return () => window.clearTimeout(timer); }, []);
  return ready ? <Home /> : <LoadingScreen />;
}

function Router() {
  return <Switch><Route path="/" component={HomeGate} /><Route path="/sign-in" component={SignIn} /><Route path="/sign-up" component={SignUp} /><Route path="/404" component={NotFound} /><Route component={NotFound} /></Switch>;
}

export default function App() {
  return <ErrorBoundary><ThemeProvider defaultTheme="dark"><TooltipProvider><Toaster position="bottom-right" duration={1000} /><Router /></TooltipProvider></ThemeProvider></ErrorBoundary>;
}
