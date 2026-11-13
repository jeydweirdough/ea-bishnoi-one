"use client";

import { AuditPage, SettingsPage, SlaPage, WorkflowsPage } from "./admin";
import { ApprovalTracking, OperationsOverview, PriorityConcerns, RequestQueue, type ModuleMeta } from "./queues";
import { TasksPage } from "./tasks";
import { AssetRegistry, ReceivingProof } from "@/components/assets/assets";
import { BocPage, RegistrationsPage } from "@/components/compliance/compliance";
import { DocumentsPage, FlightsPage, HotelsPage, RequirementsPage } from "@/components/travel/travel";
import { InventoryPage } from "@/components/inventory/inventory";
import { ContractsList, LessorsPage, RentPage } from "@/components/contracts/contracts";
import { CardsPage, CasesPage } from "@/components/banking/banking";
import { ReportsHub } from "@/components/reports/reports";
import { RenewalCalendar } from "@/components/compliance/compliance";
import { FuelBillingPage, VehiclesPage } from "@/components/fleet/fleet";

const PAGES: Record<string, () => React.ReactNode> = {
  "assets/registry": () => <AssetRegistry />,
  "assets/assignment": () => <AssetRegistry view="assigned" />,
  "assets/repairs": () => <AssetRegistry view="under_repair" />,
  "assets/receiving-proof": ReceivingProof,
  "fleet/vehicles": () => <VehiclesPage />,
  "fleet/registration-insurance": () => <VehiclesPage view="due" />,
  "fleet/fleet-cards": () => <VehiclesPage />,
  "fleet/rfid": () => <VehiclesPage />,
  "fleet/fuel-billing": FuelBillingPage,
  "compliance/registrations": () => <RegistrationsPage />,
  "compliance/sec-gis": () => <RegistrationsPage kind="sec-gis" />,
  "compliance/business-permits": () => <RegistrationsPage kind="business-permits" />,
  "compliance/boc": BocPage,
  "travel/flights": FlightsPage,
  "travel/hotels": HotelsPage,
  "travel/documents": () => <DocumentsPage />,
  "travel/employee-visas": () => <DocumentsPage view="employee-visa" />,
  "travel/expat-visas": () => <DocumentsPage view="expat-visa" />,
  "travel/renewals": () => <DocumentsPage view="expiring" />,
  "travel/requirements": RequirementsPage,
  "assets/inventory": InventoryPage,
  "contracts/lease": () => <ContractsList view="office_lease" />,
  "contracts/staff-house": () => <ContractsList view="staff_house" />,
  "contracts/registry": () => <ContractsList />,
  "contracts/renewals": () => <ContractsList view="ending" />,
  "contracts/rent": RentPage,
  "contracts/lessors": LessorsPage,
  "banking/corporate-cards": () => <CardsPage />,
  "banking/card-renewals": () => <CardsPage view="expiring" />,
  "banking/bank-requests": () => <CasesPage />,
  "banking/account-applications": () => <CasesPage view="account" />,
  "banking/documentation": () => <CasesPage view="documentation" />,
  "banking/finance-coordination": () => <CasesPage view="finance" />,
  "administration/reports": ReportsHub,
  "dashboard/upcoming-renewals": () => <RenewalCalendar />,
};

/** Renders the working screen for a live module key ("group/item"). */
export function LiveModule({ moduleKey, meta }: { moduleKey: string; meta: ModuleMeta }) {
  const [group, item] = moduleKey.split("/");
  const Page = PAGES[moduleKey];
  if (Page) return <Page />;
  if (group === "requests" && item !== "approval-tracking") return <RequestQueue meta={meta} slug={item} />;
  switch (moduleKey) {
    case "dashboard/executive-overview":
      return <OperationsOverview meta={meta} />;
    case "dashboard/pending-approvals":
    case "requests/approval-tracking":
      return <ApprovalTracking meta={meta} />;
    case "dashboard/priority-concerns":
      return <PriorityConcerns meta={meta} />;
    case "administration/tasks":
      return <TasksPage summary={meta.summary} />;
    case "administration/approvals":
      return <WorkflowsPage summary={meta.summary} />;
    case "administration/priorities-sla":
      return <SlaPage summary={meta.summary} />;
    case "administration/audit-logs":
      return <AuditPage summary={meta.summary} />;
    case "administration/settings":
      return <SettingsPage summary={meta.summary} />;
  }
  return null;
}
