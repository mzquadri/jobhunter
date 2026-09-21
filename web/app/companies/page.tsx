import { Companies } from "@/components/companies/companies";
import { TopBar } from "@/components/shell/topbar";

export const metadata = { title: "Companies" };

export default function CompaniesPage() {
  return (
    <>
      <TopBar title="Companies" subtitle="Who CareerOS watches, and how often" />
      <Companies />
    </>
  );
}
