import { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { useRouter } from "expo-router";
import { useUserStore } from "../src/stores/userStore";

export default function EntryScreen() {
  const [username, setUsername] = useState("");
  const [focused, setFocused] = useState(false);
  const router = useRouter();
  const setStoreUsername = useUserStore((state) => state.setUsername);

  const canProceed = username.trim().length > 0;

  const handleEnter = () => {
    if (!canProceed) return;
    setStoreUsername(username.trim());
    router.replace("/home");
  };

  return (
    <KeyboardAvoidingView
      className="flex-1 bg-rm-deep"
      behavior={Platform.OS === "ios" ? "padding" : "height"}
    >
      <View className="flex-1 items-center justify-center px-8">

        {/* Logo 區塊 */}
        <View
          className="w-16 h-16 rounded-2xl items-center justify-center mb-6 border border-rm-muted"
          style={{ backgroundColor: "rgba(218, 233, 244, 0.08)" }}
        >
          <Text className="text-rm-light text-2xl font-bold tracking-widest">
            RM
          </Text>
        </View>

        {/* 標題 */}
        <Text className="text-rm-light text-3xl font-bold mb-2 tracking-tight">
          RecallMap
        </Text>

        {/* 副標題 */}
        <Text className="text-rm-muted text-sm text-center mb-10 leading-relaxed">
          你的 AI 學習記憶地圖
        </Text>

        {/* 分隔線 */}
        <View className="w-full h-px bg-rm-mid mb-8 opacity-30" />

        {/* 說明文字 */}
        <Text className="text-rm-light text-base text-center mb-5 leading-relaxed w-full">
          輸入任意使用者名稱以開始使用系統
        </Text>

        {/* 輸入框 */}
        <TextInput
          className="w-full rounded-xl px-4 py-3 text-rm-light text-base mb-4"
          style={{
            backgroundColor: "rgba(218, 233, 244, 0.07)",
            borderWidth: 1,
            borderColor: focused ? "#dae9f4" : "#77919d",
          }}
          placeholder="使用者名稱"
          placeholderTextColor="#77919d"
          value={username}
          onChangeText={setUsername}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onSubmitEditing={handleEnter}
          returnKeyType="go"
          autoFocus
          autoCapitalize="none"
          autoCorrect={false}
        />

        {/* 進入按鈕 */}
        <TouchableOpacity
          className="w-full rounded-xl py-3 items-center"
          style={{
            backgroundColor: canProceed ? "#dae9f4" : "rgba(119, 145, 157, 0.25)",
          }}
          onPress={handleEnter}
          disabled={!canProceed}
          activeOpacity={0.85}
        >
          <Text
            className="text-base font-semibold"
            style={{ color: canProceed ? "#274c5e" : "#77919d" }}
          >
            開始使用
          </Text>
        </TouchableOpacity>

      </View>
    </KeyboardAvoidingView>
  );
}
