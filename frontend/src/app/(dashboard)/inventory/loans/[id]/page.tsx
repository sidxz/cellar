"use client";

import { LoanPage } from "@/features/inventory/components/loan-page";
import { use } from "react";

export default function LoanDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <LoanPage loanId={id} />;
}
