import { ApplicationsBoard } from "@/components/applications/board";
import { TopBar } from "@/components/shell/topbar";

export const metadata = { title: "Applications" };

export default function ApplicationsPage() {
  return (
    <>
      <TopBar title="Applications" subtitle="Every role you are pursuing, by stage" />
      <ApplicationsBoard />
    </>
  );
}
