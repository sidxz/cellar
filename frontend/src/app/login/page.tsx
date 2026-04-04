"use client";

import { Button } from "@/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/shared/components/ui/card";
import { useAppConfig } from "@/shared/lib/app-config";
import { useAuthz } from "@sentinel-auth/nextjs";
import { FlaskConical } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function LoginPage() {
  const { isAuthenticated, isLoading, login } = useAuthz();
  const { idpProvider } = useAppConfig();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated) {
      router.replace("/");
    }
  }, [isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-muted-foreground">Loading...</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
            <FlaskConical className="h-6 w-6 text-primary" />
          </div>
          <CardTitle className="text-2xl">Chem Vault</CardTitle>
          <CardDescription>
            Chemical compound management & screening platform
            <span className="mt-1 block text-[10px] tracking-wider text-muted-foreground/60">
              openchemvault.com
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button className="w-full" onClick={() => login(idpProvider)}>
            Sign in
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
