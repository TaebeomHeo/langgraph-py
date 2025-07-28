import { MemorySaver, Annotation, interrupt, Command, StateGraph } from "@langchain/langgraph";
import { createInterface } from 'readline/promises';
import { initializeCheckpointer } from './utils/sqliteCheckpointer.js';
import { printCurrentState, getNextNode } from './utils/printState.js';
// Define the graph state
const StateAnnotation = Annotation.Root({
    some_text: Annotation<string>({
        reducer: (a, b) => a + "\n" + b,
        default: () => "",
    })
});

function humanNode(state: typeof StateAnnotation.State) {
    const value = interrupt(
        // Any JSON serializable value to surface to the human.
        // For example, a question or a piece of text or a set of keys in the state
        {
            text_to_revise: state.some_text
        }
    );

    console.log('=== humanNode ===');
    // console.log('Input state:', JSON.stringify(state, null, 2));
    // console.log('Input state:', state.some_text);
    console.log('Original Human Input value:', JSON.stringify(value, null, 2));
    console.log('============\n');

    return {
        // Update the state with the human's input
        some_text: value + ": 사용자-- 입력값 반영/수정후 at " + new Date().toLocaleString(),
    };
}

async function main() {
    // Build the graph
    const workflow = new StateGraph(StateAnnotation)
        // Add the human-node to the graph
        .addNode("human_node", humanNode)
        .addEdge("__start__", "human_node")

    // A checkpointer is required for `interrupt` to work.
    // const checkpointer = new MemorySaver();
    const checkpointer = initializeCheckpointer();
    const graph = workflow.compile({
        checkpointer
    });

    const threadConfig = {
        configurable: { thread_id: "interrupt_function_01" },
        streamMode: "updates" as const
    };

    const currentNode = await getNextNode(graph, threadConfig);
    console.log('Current Node:', JSON.stringify(currentNode, null, 2));

    // Using stream() to directly surface the `__interrupt__` information.
    if (currentNode.isFreshStart) {
        for await (const chunk of await graph.stream(
            { some_text: "Original text at " + new Date().toLocaleString() },
            threadConfig
        )) {
            console.log("before interruptchunk:", chunk);
        }
        printCurrentState(graph, threadConfig);
        return null; // exit
    }

    const userInput = await getUserInput("사용자가 직접 입력한 값을 입력해주세요.");
    // Resume using Command
    for await (const chunk of await graph.stream(
        // new Command({ resume: " 사용자가 직접 Edited text at " + new Date().toLocaleString() }),
        new Command({ resume: `${userInput} at ${new Date().toLocaleString()}` }),
        threadConfig
    )) {
        console.log("after interrupt chunk:", chunk);
    }

    printCurrentState(graph, threadConfig);

}

// === User Input Handler ===
async function getUserInput(promptMessage: string): Promise<string> {
    const rl = createInterface({
        input: process.stdin,
        output: process.stdout
    });

    try {
        return await rl.question(`${promptMessage}: `);
    } finally {
        rl.close();
    }
}

await main();