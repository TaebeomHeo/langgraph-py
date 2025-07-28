import { type CompiledStateGraph } from "@langchain/langgraph";
import { type RunnableConfig } from "@langchain/core/runnables";

type StateType = {
    foo: string;
    bar: string[];
};

export const printStateHistory = async (
    workflow: CompiledStateGraph<StateType, any, string, any, any, any>,
    config: RunnableConfig
) => {
    console.log("\n=== State History ===");
    const stateHistory = workflow.getStateHistory(config);

    for await (const snapshot of stateHistory) {
        console.log('Timestamp:', snapshot.createdAt?.toString() ?? 'No timestamp');
        console.log('Next Node:', snapshot.next?.[0] ?? 'unknown');
        console.log('State:', JSON.stringify(snapshot.values, null, 2));
        console.log('-------------------\n');
    }
};

export const getNextNode = async (
    workflow: CompiledStateGraph<any, any, string, any, any, any>,
    config: RunnableConfig
) => {
    const snapshot = await workflow.getState(config);
    const isFreshStart = snapshot.next.length === 0;
    const nextNodeName = isFreshStart ? 'unknown' : snapshot.next[0];
    return { isFreshStart, nextNodeName };
};

export const printCurrentState = async (
    workflow: CompiledStateGraph<any, any, string, any, any, any>,
    config: RunnableConfig
) => {
    console.log("\n=== Current State ===");
    const snapshot = await workflow.getState(config);
    console.log('Values:', JSON.stringify(snapshot.values, null, 2));
    
    const { isFreshStart, nextNodeName } = await getNextNode(workflow, config);
    console.log('Next Node:', nextNodeName);
    // console.log('Is Fresh Start:', isFreshStart);
    
    console.log('-------------------\n');
}; 