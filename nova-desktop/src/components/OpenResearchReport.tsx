import { FileSearch } from "lucide-react";
import { useAppStore } from "@/stores/useAppStore";

export function OpenResearchReport({ identity }: { identity: string }) {
  const openReport = useAppStore((state) => state.openReport);
  return <button onClick={() => openReport(identity)} className="inline-flex items-center gap-2 mt-3 px-3 py-2 border border-nova-orange/30 rounded-md text-sm text-nova-orange hover:bg-nova-orange/10"><FileSearch size={16} />Open research report</button>;
}