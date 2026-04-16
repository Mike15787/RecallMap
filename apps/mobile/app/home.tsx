import { View, Text } from "react-native";
import { useUserStore } from "../src/stores/userStore";

export default function HomeScreen() {
  const username = useUserStore((state) => state.username);

  return (
    <View className="flex-1 bg-gray-950 items-center justify-center px-8">
      <Text className="text-white text-lg">
        歡迎，{username}
      </Text>
    </View>
  );
}
