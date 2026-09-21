import { Automation } from "@/components/automation/automation";
import { TopBar } from "@/components/shell/topbar";

export const metadata = { title: "Automation" };

export default function AutomationPage() {
  return (
    <>
      <TopBar title="Automation" subtitle="What the scanner is doing, and what it did" />
      <Automation />
    </>
  );
}
