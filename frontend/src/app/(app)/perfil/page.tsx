import { ProfileView } from "@/features/profile/components/ProfileView";

export const metadata = { title: "Mi perfil · Vigía" };

export default function ProfilePage() {
  return (
    <div className="page">
      <h1>Mi perfil</h1>
      <ProfileView />
    </div>
  );
}
