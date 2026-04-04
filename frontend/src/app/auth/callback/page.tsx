"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { AuthzCallback } from "@sentinel-auth/nextjs";
import { FlaskConical } from "lucide-react";
import { useRouter } from "next/navigation";

export default function CallbackPage() {
  const router = useRouter();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <AuthzCallback
        onSuccess={() => router.replace("/")}
        onError={(error) => router.replace(`/login?error=${encodeURIComponent(error.message)}`)}
        loadingComponent={
          <Card className="w-full max-w-sm">
            <CardHeader className="text-center">
              <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <FlaskConical className="h-6 w-6 text-primary" />
              </div>
              <CardTitle className="text-2xl">Signing in...</CardTitle>
              <CardDescription>Authenticating with your identity provider</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </CardContent>
          </Card>
        }
        workspaceSelector={({ workspaces, onSelect, isLoading: selecting }) => (
          <Card className="w-full max-w-sm">
            <CardHeader className="text-center">
              <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                <FlaskConical className="h-6 w-6 text-primary" />
              </div>
              <CardTitle className="text-2xl">Select Workspace</CardTitle>
              <CardDescription>Choose a workspace to continue</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {workspaces.map((ws) => (
                <Button
                  key={ws.id}
                  variant="outline"
                  className="w-full justify-start"
                  disabled={selecting}
                  onClick={() => onSelect(ws.id)}
                >
                  <span className="truncate">{ws.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{ws.role}</span>
                </Button>
              ))}
            </CardContent>
          </Card>
        )}
      />
    </div>
  );
}
