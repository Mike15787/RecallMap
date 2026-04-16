import { create } from "zustand";

interface IUserStore {
  username: string | null;
  setUsername: (name: string) => void;
  clear: () => void;
}

export const useUserStore = create<IUserStore>((set) => ({
  username: null,
  setUsername: (name) => set({ username: name }),
  clear: () => set({ username: null }),
}));
