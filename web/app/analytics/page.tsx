import { Analytics } from "@/components/analytics/analytics";
import { TopBar } from "@/components/shell/topbar";

export const metadata = { title: "Analytics" };

export default function AnalyticsPage() {
  return (
    <>
      <TopBar title="Analytics" subtitle="What the market looks like for your profile" />
      <Analytics />
    </>
  );
}
