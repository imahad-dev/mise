import React from "react";
import { NeutralLoader } from "../../../components/NeutralLoader";

export default function Loading() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-white">
      <NeutralLoader label="Loading" />
    </main>
  );
}
