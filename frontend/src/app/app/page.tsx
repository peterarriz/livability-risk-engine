import AppWorkspace from "@/components/app-workspace";

type AppPageProps = {
  searchParams: Promise<{ address?: string | string[] }>;
};

export default async function AppPage({ searchParams }: AppPageProps) {
  const params = await searchParams;
  const rawAddress = Array.isArray(params.address) ? params.address[0] : params.address;
  return <AppWorkspace initialAddress={rawAddress ?? ""} />;
}
