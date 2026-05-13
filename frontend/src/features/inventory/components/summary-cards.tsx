"use client";

import { AlertTriangle, Clock, ClipboardList, Activity } from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Skeleton } from "@/shared/components/ui/skeleton";
import { useInventorySummary } from "../hooks/use-inventory-summary";
import type { InventorySummary } from "../types";

interface SummaryCardsProps {
  onLowStockClick: () => void;
  onExpiringClick: () => void;
  onPendingRequestsClick: () => void;
}

interface MetricCardProps {
  icon: React.ReactNode;
  count: number;
  label: string;
  onClick: () => void;
}

function MetricCard({ icon, count, label, onClick }: MetricCardProps) {
  const hasAlert = count > 0;

  return (
    <Card
      className={`cursor-pointer transition-colors hover:bg-accent/50 ${
        hasAlert ? "border-warning/50" : ""
      }`}
      onClick={onClick}
    >
      <CardContent className="flex items-center gap-4 py-4">
        <div
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
            hasAlert
              ? "bg-warning/10 text-warning"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {icon}
        </div>
        <div>
          <p
            className={`text-2xl font-bold leading-none ${
              hasAlert ? "text-warning" : "text-foreground"
            }`}
          >
            {count}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

interface ActivityCardProps {
  summary: InventorySummary;
}

function ActivityCard({ summary }: ActivityCardProps) {
  const items = summary.recent_activity.slice(0, 3);

  return (
    <Card>
      <CardContent className="py-4">
        <div className="mb-2 flex items-center gap-2">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Activity className="h-5 w-5" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">
            Recent Activity
          </p>
        </div>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent activity.</p>
        ) : (
          <ul className="space-y-1">
            {items.map((item) => (
              <li
                key={item.entity_id}
                className="truncate text-xs text-muted-foreground"
                title={item.description}
              >
                {item.description}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function SummaryCards({
  onLowStockClick,
  onExpiringClick,
  onPendingRequestsClick,
}: SummaryCardsProps) {
  const { data: summary, isLoading } = useInventorySummary();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard
        icon={<AlertTriangle className="h-5 w-5" />}
        count={summary.low_stock_count}
        label="Low Stock"
        onClick={onLowStockClick}
      />
      <MetricCard
        icon={<Clock className="h-5 w-5" />}
        count={summary.expiring_soon_count}
        label="Expiring (30d)"
        onClick={onExpiringClick}
      />
      <MetricCard
        icon={<ClipboardList className="h-5 w-5" />}
        count={summary.pending_requests_count}
        label="Pending Requests"
        onClick={onPendingRequestsClick}
      />
      <ActivityCard summary={summary} />
    </div>
  );
}
