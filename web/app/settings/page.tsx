import { Settings } from "@/components/settings/settings";
import { TopBar } from "@/components/shell/topbar";

export const metadata = { title: "Settings" };

export default function SettingsPage() {
  return (
    <>
      <TopBar title="Settings" subtitle="What CareerOS looks for, and how it scores it" />
      <Settings />
    </>
  );
}
