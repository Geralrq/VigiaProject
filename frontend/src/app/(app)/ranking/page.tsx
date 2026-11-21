import { RankingList } from "@/features/ranking/components/RankingList";

export const metadata = { title: "Ranking · Vigía" };

export default function RankingPage() {
  return (
    <div className="page">
      <h1>Ranking de voluntarios</h1>
      <RankingList />
    </div>
  );
}
