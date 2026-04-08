"use client";

import {
  FlaskConical,
  Boxes,
  Package,
  TestTubes,
  Activity,
  Plus,
  Search,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/page-header";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useDashboardStats } from "../hooks/use-dashboard";

interface StatCardProps {
  title: string;
  value: number;
  icon: React.ReactNode;
  href: string;
}

function StatCard({ title, value, icon, href }: StatCardProps) {
  return (
    <Link href={href}>
      <Card className="transition-colors hover:bg-muted/50">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            {title}
          </CardTitle>
          {icon}
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-bold tabular-nums">{value.toLocaleString()}</p>
        </CardContent>
      </Card>
    </Link>
  );
}

export function Dashboard() {
  const { data: stats, isLoading } = useDashboardStats();

  return (
    <div className="space-y-8">
      <PageHeader
        title="Dashboard"
        subtitle="Overview of your workspace activity."
      />

      {/* Stats grid */}
      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[108px]" />
          ))}
        </div>
      ) : stats ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard
            title="Compounds"
            value={stats.total_compounds}
            icon={<FlaskConical className="h-4 w-4 text-muted-foreground" />}
            href="/compounds"
          />
          <StatCard
            title="Batches"
            value={stats.total_batches}
            icon={<Boxes className="h-4 w-4 text-muted-foreground" />}
            href="/inventory"
          />
          <StatCard
            title="Samples"
            value={stats.total_samples}
            icon={<Package className="h-4 w-4 text-muted-foreground" />}
            href="/inventory"
          />
          <StatCard
            title="Active Protocols"
            value={stats.active_protocols}
            icon={<TestTubes className="h-4 w-4 text-muted-foreground" />}
            href="/assays"
          />
          <StatCard
            title="Runs"
            value={stats.total_runs}
            icon={<Activity className="h-4 w-4 text-muted-foreground" />}
            href="/assays"
          />
        </div>
      ) : null}

      {/* Quick actions */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button asChild>
            <Link href="/compounds">
              <Plus className="mr-2 h-4 w-4" />
              Register Compound
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/assays">
              <TestTubes className="mr-2 h-4 w-4" />
              Create Protocol
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/compounds">
              <Search className="mr-2 h-4 w-4" />
              Search Compounds
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
